import os

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, Command
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


CONTROLLERS = [
    "joint_state_broadcaster",
    "diff_drive_controller",
    "lift_position_controller",
    "gripper_position_controller",
]


def robot_nodes(ns, x, y, yaw):
    share = get_package_share_directory("robocon2027_competition_simulator")

    xacro_file = os.path.join(
        share, "urdf", "competition_robot.urdf.xacro"
    )
    controller_yaml = os.path.join(
        share, "config", f"controllers_{ns}.yaml"
    )

    robot_description = Command([
        "xacro ",
        xacro_file,
        " prefix:=",
        ns,
        "/ robot_ns:=",
        ns,
    ])

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        namespace=ns,
        name="robot_state_publisher",
        output="screen",
        parameters=[
            {
                "robot_description": robot_description,
                "use_sim_time": True,
            }
        ],
        remappings=[
            ("/tf", "tf"),
            ("/tf_static", "tf_static"),
        ],
    )

    spawn_robot = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=[
            "-name", ns,
            "-topic", f"/{ns}/robot_description",
            "-x", str(x),
            "-y", str(y),
            "-z", "0.0",
            "-Y", str(yaw),
        ],
        output="screen",
    )

    lidar_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=[
            f"/{ns}/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan"
        ],
        remappings=[
            (f"/{ns}/scan", "scan"),
        ],
        namespace=ns,
        output="screen",
    )

    # Pass the same per-robot YAML explicitly to each controller spawner.
    # The YAML contains the controller-specific parameter sections:
    # /robotN/diff_drive_controller, /robotN/lift_position_controller,
    # and /robotN/gripper_position_controller.
    spawners = []
    for controller in CONTROLLERS:
        spawners.append(
            Node(
                package="controller_manager",
                executable="spawner",
                arguments=[
                    controller,
                    "--controller-manager",
                    f"/{ns}/controller_manager",
                    "--param-file",
                    controller_yaml,
                    "--controller-manager-timeout",
                    "60",
                ],
                output="screen",
            )
        )

    slam = Node(
        package="slam_toolbox",
        executable="async_slam_toolbox_node",
        namespace=ns,
        name="slam_toolbox",
        output="screen",
        parameters=[
            os.path.join(share, "config", "slam.yaml"),
            {
                "use_sim_time": True,
                "map_frame": f"{ns}/map",
                "odom_frame": f"{ns}/odom",
                "base_frame": f"{ns}/base_link",
                "scan_topic": "scan",
            },
        ],
        remappings=[
            ("/tf", "tf"),
            ("/tf_static", "tf_static"),
        ],
    )

    nav2_share = get_package_share_directory("nav2_bringup")
    nav2_launch = os.path.join(
        nav2_share, "launch", "navigation_launch.py"
    )
    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(nav2_launch),
        launch_arguments={
            "namespace": ns,
            "use_sim_time": "True",
            "autostart": "True",
            "params_file": os.path.join(
                share, "config", f"nav2_{ns}.yaml"
            ),
            "use_composition": "False",
            "respawn": "False",
        }.items(),
    )

    return {
        "rsp": robot_state_publisher,
        "spawn": spawn_robot,
        "bridge": lidar_bridge,
        "spawners": spawners,
        "slam": slam,
        "nav2": nav2,
    }


def generate_launch_description():
    share = get_package_share_directory("robocon2027_competition_simulator")
    world = os.path.join(
        share, "worlds", "competition_arena.sdf"
    )

    nav = LaunchConfiguration("start_navigation")

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory("ros_gz_sim"),
                "launch",
                "gz_sim.launch.py",
            )
        ),
        launch_arguments={
            "gz_args": ["-r -v 3 ", world]
        }.items(),
    )

    clock_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=[
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"
        ],
        output="screen",
    )

    robot1 = robot_nodes("robot1", -4.7, -4.7, 0.785398)
    robot2 = robot_nodes("robot2", 4.7, 4.7, -2.35619)

    competition_manager = Node(
        package="robocon2027_competition_simulator",
        executable="competition_manager",
        output="screen",
        parameters=[
            {"match_duration_sec": 180.0}
        ],
    )

    actions = [
        gazebo,
        clock_bridge,
        robot1["rsp"],
        robot2["rsp"],

        # Spawn both robot models after Gazebo and robot_description
        # publishers have had time to start.
        TimerAction(
            period=4.0,
            actions=[
                robot1["spawn"],
                robot2["spawn"],
            ],
        ),

        robot1["bridge"],
        robot2["bridge"],

        # Stagger spawner startup to avoid racing controller-manager
        # service calls. Both robots use their own controller YAML.
        TimerAction(
            period=10.0,
            actions=[
                robot1["spawners"][0],
                robot2["spawners"][0],
            ],
        ),
        TimerAction(
            period=12.0,
            actions=[
                robot1["spawners"][1],
                robot2["spawners"][1],
            ],
        ),
        TimerAction(
            period=14.0,
            actions=[
                robot1["spawners"][2],
                robot2["spawners"][2],
            ],
        ),
        TimerAction(
            period=16.0,
            actions=[
                robot1["spawners"][3],
                robot2["spawners"][3],
            ],
        ),

        competition_manager,
    ]

    navigation_actions = [
        robot1["slam"],
        robot1["nav2"],
        robot2["slam"],
        robot2["nav2"],
    ]

    return LaunchDescription([
        DeclareLaunchArgument(
            "start_navigation",
            default_value="true",
        ),
        *actions,
        TimerAction(
            period=20.0,
            actions=navigation_actions,
            condition=IfCondition(nav),
        ),
    ])
