
import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    GroupAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution

from launch_ros.actions import PushRosNamespace, SetRemap
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():

    # Package chứa cấu hình SLAM của robot_competition
    package_share = get_package_share_directory(
        'robot_competition'
    )

    default_slam_params = os.path.join(
        package_share,
        'config',
        'slam_robot1.yaml',
    )

    slam_params_file = LaunchConfiguration(
        'slam_params_file'
    )

    # Đường dẫn online_async_launch.py của SLAM Toolbox
    slam_launch_file = PathJoinSubstitution([
        FindPackageShare('slam_toolbox'),
        'launch',
        'online_async_launch.py',
    ])

    # SLAM Toolbox cho robot1
    slam_toolbox = GroupAction(
        actions=[

            # Namespace riêng của robot1
            PushRosNamespace('robot1'),

            # TF riêng cho robot1
            SetRemap(src='/tf', dst='tf'),
            SetRemap(src='/tf_static', dst='tf_static'),
            # Map riêng cho robot1
            SetRemap(src='/map', dst='map'),
            SetRemap(src='/map_metadata', dst='map_metadata'),
            # Gọi online_async_launch.py
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    slam_launch_file
                ),
                launch_arguments={
                    'use_sim_time': 'true',
                    'slam_params_file': slam_params_file,
                }.items(),
            ),
        ]
    )

    return LaunchDescription([

        DeclareLaunchArgument(
            'slam_params_file',
            default_value=default_slam_params,
            description='File tham so SLAM Toolbox',
        ),

        slam_toolbox,

    ])

