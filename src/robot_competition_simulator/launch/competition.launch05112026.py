import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, Command
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory

def robot_nodes(ns, x, y, yaw, color):
    share = get_package_share_directory('robot_competition')
    xacro = os.path.join(share, 'urdf', 'competition_robot.urdf.xacro')
    desc = Command(['xacro ', xacro, ' prefix:=', ns, '/', ' robot_ns:=', ns,' robot_color:=', color])
    rsp = Node(package='robot_state_publisher', executable='robot_state_publisher',
               namespace=ns, name='robot_state_publisher', output='screen',
               parameters=[{'robot_description': desc, 'use_sim_time': True}],
               remappings=[('/tf', 'tf'), ('/tf_static', 'tf_static')])
    spawn = Node(package='ros_gz_sim', executable='create',
                 arguments=['-name', ns, '-topic', f'/{ns}/robot_description',
                            '-x', str(x), '-y', str(y), '-z', '0.0', '-Y', str(yaw)],
                 output='screen')
    bridges = Node(package='ros_gz_bridge', executable='parameter_bridge',
                   arguments=[f'/{ns}/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan'],
                   remappings=[(f'/{ns}/scan', 'scan')], namespace=ns, output='screen')
    spawners = [
        Node(package='controller_manager', executable='spawner',
             namespace=ns,
             arguments=[
                 controller,
                 '--controller-manager', f'/{ns}/controller_manager',
                 '--param-file', os.path.join(
                     share, 'config', f'controllers_{ns}.yaml'
                 ),
                 '--controller-manager-timeout', '60',
             ],
             output='screen')
        for controller in ['joint_state_broadcaster', 'diff_drive_controller',
                           'lift_position_controller', 'gripper_position_controller']
    ]
    slam = Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        namespace=ns,
        name='slam_toolbox',
        output='screen',
        parameters=[
            os.path.join(share, 'config', 'slam.yaml'),
            {
                'use_sim_time': True,
                'map_frame': f'{ns}/map',
                'odom_frame': f'{ns}/odom',
                'base_frame': f'{ns}/base_footprint',
                'scan_topic': 'scan'
            }
        ],
        remappings=[
            ('/tf', 'tf'),
            ('/tf_static', 'tf_static'),
            ('/map', f'/{ns}/map'),
            ('/map_metadata', f'/{ns}/map_metadata'),
        ]
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
            'node_names': ['slam_toolbox']
        }]
    )             
                
                
                
    nav2_share = get_package_share_directory('nav2_bringup')
    nav2_file = os.path.join(nav2_share, 'launch', 'navigation_launch.py')
    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(nav2_file),
        launch_arguments={'namespace': ns, 'use_sim_time': 'True',
                          'autostart': 'True',
                          'params_file': os.path.join(share, 'config', f'nav2_{ns}.yaml'),
                          'use_composition': 'False', 'respawn': 'False'}.items())
    return rsp, spawn, bridges, spawners, slam, nav2, slam_lifecycle_manager

def generate_launch_description():
    share = get_package_share_directory('robot_competition')
    world = os.path.join(share, 'worlds', 'competition_arena.sdf')
    gui = LaunchConfiguration('gui')
    nav = LaunchConfiguration('start_navigation')
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('ros_gz_sim'), 'launch', 'gz_sim.launch.py')),
        launch_arguments={'gz_args': ['-r -v 3 ', world]}.items())
    clock = Node(package='ros_gz_bridge', executable='parameter_bridge',
                 arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'],
                 output='screen')
    robot1_color = LaunchConfiguration('robot1_color')
    robot2_color = LaunchConfiguration('robot2_color')
    r1 = robot_nodes('robot1', -4.7, -4.7, 0.785398, robot1_color)
    r2 = robot_nodes('robot2', 4.7, 4.7, -2.35619, robot2_color)
    manager = Node(package='robot_competition', executable='competition_manager',
                   output='screen', parameters=[{'match_duration_sec': 180.0}])
    actions = [gazebo, clock, r1[0], r2[0],
               TimerAction(period=4.0, actions=[r1[1], r2[1]]),
               r1[2], r2[2],
               TimerAction(period=10.0, actions=r1[3] + r2[3]),
               manager]
    nav_actions = [
        r1[4], r2[4],
        r1[5], r2[5]
    ]

    slam_manager_actions = [
        r1[6], r2[6]
    ]
    return LaunchDescription([
    DeclareLaunchArgument('gui', default_value='true'),

    DeclareLaunchArgument(
        'start_navigation',
        default_value='true'
    ),

    DeclareLaunchArgument(
        'robot1_color',
        default_value='blue',
        description='Robot 1 body color'
    ),

    DeclareLaunchArgument(
        'robot2_color',
        default_value='red',
        description='Robot 2 body color'
    ),

    *actions,
    TimerAction(
        period=18.0,
        actions=nav_actions,
        condition=IfCondition(nav)
    ),
    TimerAction(
        period=20.0,
        actions=slam_manager_actions,
        condition=IfCondition(nav)
    )
    ])
