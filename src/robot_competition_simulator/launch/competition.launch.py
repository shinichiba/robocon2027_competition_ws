#!/usr/bin/env python3
"""Staged launch for a two-robot Gazebo / ROS 2 Lyrical competition."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    LogError,
    LogInfo,
    RegisterEventHandler,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node


CONTROLLERS = (
    'joint_state_broadcaster',
    'diff_drive_controller',
    'lift_position_controller',
    'gripper_position_controller',
)


def make_robot(ns, x, y, yaw, color, package_share):
    """Create one robot's nodes. Controller spawners are launched sequentially."""
    xacro_file = os.path.join(
        package_share, 'urdf', 'competition_robot.urdf.xacro'
    )
    controller_file = os.path.join(
        package_share, 'config', f'controllers_{ns}.yaml'
    )

    robot_description = Command([
        'xacro ', xacro_file,
        ' prefix:=', ns, '/',
        ' robot_ns:=', ns,
        ' robot_color:=', color,
    ])

    state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        namespace=ns,
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': True,
        }],
        remappings=[('/tf', 'tf'), ('/tf_static', 'tf_static')],
    )

    spawn = Node(
        package='ros_gz_sim',
        executable='create',
        name=f'{ns}_spawn',
        arguments=[
            '-name', ns,
            '-topic', f'/{ns}/robot_description',
            '-x', str(x),
            '-y', str(y),
            '-z', '0.0',
            '-Y', str(yaw),
        ],
        output='screen',
    )

    # Bridge the absolute Gazebo topic to the same absolute ROS topic.
    # This avoids relying on namespace-relative remapping for sensor data.
    scan_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name=f'{ns}_scan_bridge',
        arguments=[
            f'/{ns}/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan'
        ],
        output='screen',
    )

    spawners = []
    for controller in CONTROLLERS:
        spawners.append(Node(
            package='controller_manager',
            executable='spawner',
            namespace=ns,
            name=f'spawner_{controller}',
            arguments=[
                controller,
                '--controller-manager', f'/{ns}/controller_manager',
                '--param-file', controller_file,
                '--controller-manager-timeout', '120',
            ],
            output='screen',
        ))

    slam = Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        namespace=ns,
        name='slam_toolbox',
        output='screen',
        parameters=[
            os.path.join(package_share, 'config', 'slam.yaml'),
            {
                'use_sim_time': True,
                'map_frame': f'{ns}/map',
                'odom_frame': f'{ns}/odom',
                'base_frame': f'{ns}/base_footprint',
                'scan_topic': 'scan',
            },
        ],
        remappings=[
            ('/tf', 'tf'),
            ('/tf_static', 'tf_static'),
            ('/map', f'/{ns}/map'),
            ('/map_metadata', f'/{ns}/map_metadata'),
        ],
    )

    slam_lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        namespace=ns,
        name='lifecycle_manager_slam',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'autostart': True,
            'bond_timeout': 10.0,
            'node_names': ['slam_toolbox'],
        }],
    )

    nav2_launch_file = os.path.join(
        get_package_share_directory('nav2_bringup'),
        'launch', 'navigation_launch.py',
    )
    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(nav2_launch_file),
        launch_arguments={
            'namespace': ns,
            'use_sim_time': 'True',
            'autostart': 'True',
            'params_file': os.path.join(
                package_share, 'config', f'nav2_{ns}.yaml'
            ),
            'use_composition': 'False',
            # Do not respawn a node that repeatedly segfaults; expose the
            # original error instead of creating a rapid crash/restart loop.
            'respawn': 'False',
        }.items(),
    )

    return {
        'namespace': ns,
        'state_publisher': state_publisher,
        'spawn': spawn,
        'scan_bridge': scan_bridge,
        'spawners': spawners,
        'slam': slam,
        'slam_manager': slam_lifecycle_manager,
        'nav2': nav2,
    }


def generate_launch_description():
    package_share = get_package_share_directory('robot_competition')
    world_file = os.path.join(
        package_share, 'worlds', 'competition_arena.sdf'
    )

    robot1 = make_robot(
        'robot1', -4.7, -4.7, 0.785398,
        LaunchConfiguration('robot1_color'), package_share,
    )
    robot2 = make_robot(
        'robot2', 4.7, 4.7, -2.35619,
        LaunchConfiguration('robot2_color'), package_share,
    )

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('ros_gz_sim'),
            'launch', 'gz_sim.launch.py',
        )),
        launch_arguments={
            'gz_args': ['-r -v 2 ', world_file],
        }.items(),
    )

    clock_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='clock_bridge',
        arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'],
        output='screen',
    )

    competition_manager = Node(
        package='robot_competition',
        executable='competition_manager',
        name='competition_manager',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'match_duration_sec': 180.0,
        }],
    )
    odom_tf_splitter = Node(
    package='robot_competition',
    executable='odom_tf_splitter',
    name='odom_tf_splitter',
    output='screen',
    parameters=[
        {'use_sim_time': True}
        ]   
    )
    # This node ONLY reads the two isolated TF trees and publishes
    # a visualization copy on /tf_viz and /tf_static_viz.
    # It does not publish to /tf or /tf_static.
    tf_aggregator = Node(
        package='robot_competition',
        executable='tf_aggregator',
        name='tf_aggregator',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            # Visualization-only anchors: map frames are placed at the
            # corresponding initial Gazebo spawn poses.
            'robot1_map_x': -4.7,
            'robot1_map_y': -4.7,
            'robot1_map_yaw': 0.785398,
            'robot2_map_x': 4.7,
            'robot2_map_y': 4.7,
            'robot2_map_yaw': -2.35619,
        }]
    )

    # A robot is considered ready only after all four controller spawners
    # have exited successfully. Once BOTH robots are ready, start SLAM.
    ready_robots = set()

    def robot_ready_callback(robot_name):
        def _on_exit(event, context):
            if event.returncode != 0:
                return [LogError(
                    msg=f'[{robot_name}] controller spawner failed '
                        f'(exit code {event.returncode}); stopping staged startup.'
                )]

            ready_robots.add(robot_name)
            if len(ready_robots) < 2:
                return [LogInfo(
                    msg=f'[{robot_name}] controllers ready; waiting for the other robot.'
                )]

            actions = [
                LogInfo(msg='Both robots are spawned and their controllers are active.'),
                competition_manager,odom_tf_splitter,tf_aggregator,
            ]
                # Start SLAM independently from Nav2
            if LaunchConfiguration('start_slam').perform(context).lower() == 'true':
                actions.append(TimerAction(
                period=2.0,
                actions=[robot1['slam'], robot2['slam']]
                 ))
                # Start lifecycle managers only after the SLAM processes exist.
                actions.append(TimerAction(
                period=5.0,
                actions=[
                robot1['slam_manager'], robot2['slam_manager']
                ]
                ))
             # Start Nav2 only when requested
            if LaunchConfiguration('start_navigation').perform(context).lower() == 'true':
                actions.append(TimerAction(
                period=13.0,
                actions=[robot1['nav2'], robot2['nav2']]
                ))
            return actions
        return _on_exit

    event_handlers = []
    for robot in (robot1, robot2):
        ns = robot['namespace']
        spawners = robot['spawners']

        # Spawn the entity first. Only after ros_gz_sim/create exits
        # successfully do we start the sensor bridge and first controller.
        def after_spawn(event, context, scan_bridge=robot['scan_bridge'],
                        first_spawner=spawners[0], robot_name=ns):
            if event.returncode != 0:
                return [LogError(
                    msg=f'[{robot_name}] Gazebo spawn failed '
                        f'(exit code {event.returncode}); controller startup skipped.'
                )]
            return [
                scan_bridge,
                TimerAction(period=1.0, actions=[first_spawner]),
            ]

        event_handlers.append(RegisterEventHandler(OnProcessExit(
            target_action=robot['spawn'],
            on_exit=after_spawn,
        )))

        # Serialize controller loading for each controller_manager.
        for index in range(len(spawners) - 1):
            current_spawner = spawners[index]
            next_spawner = spawners[index + 1]
            controller_name = CONTROLLERS[index]

            def next_controller(event, context, next_action=next_spawner,
                                robot_name=ns, current_name=controller_name):
                if event.returncode != 0:
                    return [LogError(
                        msg=f'[{robot_name}] {current_name} failed '
                            f'(exit code {event.returncode}); remaining controllers skipped.'
                    )]
                return [TimerAction(period=0.5, actions=[next_action])]

            event_handlers.append(RegisterEventHandler(OnProcessExit(
                target_action=current_spawner,
                on_exit=next_controller,
            )))

        # The last spawner is the readiness signal for this robot.
        event_handlers.append(RegisterEventHandler(OnProcessExit(
            target_action=spawners[-1],
            on_exit=robot_ready_callback(ns),
        )))

    return LaunchDescription([
        DeclareLaunchArgument(
            'start_slam',
            default_value='true',
            description='Start SLAM Toolbox'
        ),
        DeclareLaunchArgument(
            'start_navigation', default_value='true',
            description='Start SLAM Toolbox and Nav2 after both robots are ready',
        ),
        DeclareLaunchArgument(
            'robot1_color', default_value='blue',
            description='Robot 1 body color',
        ),
        DeclareLaunchArgument(
            'robot2_color', default_value='red',
            description='Robot 2 body color',
        ),
        gazebo,
        clock_bridge,
        robot1['state_publisher'],
        robot2['state_publisher'],
        # Give robot_state_publisher time to publish robot_description before spawn.
        TimerAction(
            period=3.0,
            actions=[robot1['spawn'], robot2['spawn']],
        ),
        *event_handlers,
    ])
