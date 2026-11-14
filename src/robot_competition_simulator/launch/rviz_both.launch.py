import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    # 1. Tim duong dan file RViz mac dinh trong package
    package_share = get_package_share_directory('robot_competition')

    default_rviz_config = os.path.join(
        package_share,
        'rviz',
        'both_robots.rviz'
    )

    # 2. Khai bao cac tham so launch
    rviz_config = LaunchConfiguration('rviz_config')

    robot1_map_x = LaunchConfiguration('robot1_map_x')
    robot1_map_y = LaunchConfiguration('robot1_map_y')
    robot1_map_yaw = LaunchConfiguration('robot1_map_yaw')

    robot2_map_x = LaunchConfiguration('robot2_map_x')
    robot2_map_y = LaunchConfiguration('robot2_map_y')
    robot2_map_yaw = LaunchConfiguration('robot2_map_yaw')

    return LaunchDescription([

        # 3. File RViz mac dinh
        DeclareLaunchArgument(
            'rviz_config',
            default_value=default_rviz_config,
            description='Duong dan file cau hinh RViz2'
        ),

        # 4. Vi tri map robot1 trong he toa do world
        DeclareLaunchArgument('robot1_map_x', default_value='0.0'),
        DeclareLaunchArgument('robot1_map_y', default_value='0.0'),
        DeclareLaunchArgument('robot1_map_yaw', default_value='0.0'),

        # 5. Vi tri map robot2 trong he toa do world
        DeclareLaunchArgument('robot2_map_x', default_value='0.0'),
        DeclareLaunchArgument('robot2_map_y', default_value='0.0'),
        DeclareLaunchArgument('robot2_map_yaw', default_value='0.0'),

        # 6. Tong hop TF cua hai robot
        Node(
            package='robot_competition',
            executable='tf_aggregator',
            name='tf_aggregator',
            output='screen',
            parameters=[{'use_sim_time': True}],
        ),

        # 7. Gan map robot1 vao world
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='robot1_map_to_world',
            output='screen',
            arguments=[
                '--x', robot1_map_x,
                '--y', robot1_map_y,
                '--z', '0',
                '--yaw', robot1_map_yaw,
                '--pitch', '0',
                '--roll', '0',
                '--frame-id', 'world',
                '--child-frame-id', 'robot1/map',
            ],
            parameters=[{'use_sim_time': True}],
        ),

        # 8. Gan map robot2 vao world
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='robot2_map_to_world',
            output='screen',
            arguments=[
                '--x', robot2_map_x,
                '--y', robot2_map_y,
                '--z', '0',
                '--yaw', robot2_map_yaw,
                '--pitch', '0',
                '--roll', '0',
                '--frame-id', 'world',
                '--child-frame-id', 'robot2/map',
            ],
            parameters=[{'use_sim_time': True}],
        ),

        # 9. Mo RViz2 hien thi ca hai robot
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2_both_robots',
            output='screen',
            arguments=['-d', rviz_config],
            parameters=[{'use_sim_time': True}],
        ),
    ])

