#!/usr/bin/env python3
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    package_share = get_package_share_directory('robot_competition')
    default_rviz_config = os.path.join(
        package_share, 'rviz', 'robot1_slam.rviz'
    )

    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2_robot1',
        namespace='robot1',
        output='screen',
        arguments=['-d', LaunchConfiguration('rviz_config')],
        parameters=[
        {'use_sim_time': True}
        ],
        remappings=[
            ('/tf', '/robot1/tf'),
            ('/tf_static', '/robot1/tf_static'),
        ],
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'rviz_config',
            default_value=default_rviz_config,
            description='Path to RViz2 configuration',
        ),
        rviz_node,
    ])
