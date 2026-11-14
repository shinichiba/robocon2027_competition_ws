
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():

    package_share = get_package_share_directory(
        'robot_competition'
    )

    nav2_share = get_package_share_directory(
        'nav2_bringup'
    )

    default_map = os.path.join(
        package_share,
        'robot_maps',
        'robot1_map.yaml'
    )

    nav2_params = os.path.join(
        package_share,
        'config',
        'nav2_robot1.yaml'
    )

    map_file = LaunchConfiguration('map')
    params_file = LaunchConfiguration('params_file')

    bringup_launch_file = os.path.join(
        nav2_share,
        'launch',
        'bringup_launch.py'
    )

    nav2_bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(bringup_launch_file),

        launch_arguments={
            'namespace': 'robot1',
            'map': map_file,
            'use_sim_time': 'True',
            'autostart': 'True',
            'params_file': params_file,
            'use_composition': 'False',
            'use_respawn': 'False',
            'slam': 'False',
        }.items()
    )

    return LaunchDescription([

        DeclareLaunchArgument(
            'map',
            default_value=default_map,
            description='Map YAML file'
        ),

        DeclareLaunchArgument(
            'params_file',
            default_value=nav2_params,
            description='Nav2 parameters'
        ),

        nav2_bringup,
    ])

