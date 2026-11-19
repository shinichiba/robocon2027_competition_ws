
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    package_share = get_package_share_directory(
        'robocon2027_competition_simulator'
    )

    default_slam_params = os.path.join(
        package_share,
        'config',
        'slam.yaml',
    )

    slam_params_file = LaunchConfiguration(
        'slam_params_file'
    )

    # SLAM Toolbox cho robot1
    slam_toolbox = Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        output='screen',
        namespace='robot1',
        parameters=[
            slam_params_file,
            {
                'use_sim_time': True,
                'min_laser_range': 0.12,
                'max_laser_range': 11.5,
                'map_frame': 'robot1/map',
                'odom_frame': 'robot1/odom',
                'base_frame': 'robot1/base_footprint',
                # Topic scan tương đối trong namespace robot1
                'scan_topic': 'robot1/scan',
            },
        ],

        # Duy trì TF riêng của robot1
        remappings=[
            ('/tf', 'tf'),
            ('/tf_static', 'tf_static'),
            ('/map', 'map'),
            ('/map_metadata', 'map_metadata'),
        ],
    )

    # Lifecycle manager kích hoạt SLAM Toolbox
    slam_lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        namespace='robot1',
        name='lifecycle_manager_slam',
        output='screen',

        parameters=[{
            'use_sim_time': True,
            'autostart': True,
            'bond_timeout': 10.0,
            'node_names': ['slam_toolbox'],
        }],
    )

    return LaunchDescription([

        DeclareLaunchArgument(
            'slam_params_file',
            default_value=default_slam_params,
            description='File tham so SLAM Toolbox'
        ),
        slam_toolbox,
        slam_lifecycle_manager,
    ])

