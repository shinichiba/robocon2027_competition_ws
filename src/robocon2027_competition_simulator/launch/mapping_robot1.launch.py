import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, RegisterEventHandler
from launch.events import matches_action
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import LifecycleNode
from launch_ros.event_handlers import OnStateTransition
from launch_ros.events.lifecycle import ChangeState
from lifecycle_msgs.msg import Transition


def generate_launch_description():
    package_share = get_package_share_directory(
        'robocon2027_competition_simulator'
    )

    default_slam_params = os.path.join(
        package_share,
        'config',
        'slam.yaml',
    )

    slam_params_file = LaunchConfiguration('slam_params_file')

    # Khai báo dưới dạng LifecycleNode để điều khiển chuyển trạng thái trực tiếp
    slam_toolbox = LifecycleNode(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        namespace='robot1',
        output='screen',
        parameters=[
            slam_params_file,
            {
                'use_sim_time': True,
                # Tắt bond để tránh lỗi bad_weak_ptr
                'use_lifecycle_manager': False,
                'min_laser_range': 0.30,
                'max_laser_range': 8.0,
                'map_frame': 'robot1/map',
                'odom_frame': 'robot1/odom',
                'base_frame': 'robot1/base_footprint',
                'scan_topic': '/robot1/scan',
            },
        ],
        remappings=[
            ('/tf', 'tf'),
            ('/tf_static', 'tf_static'),
            ('/map', 'map'),
            ('/map_metadata', 'map_metadata'),
        ],
    )

    # Bước 1: Tự động gửi lệnh CONFIGURE ngay khi node khởi tạo
    configure_event = EmitEvent(
        event=ChangeState(
            lifecycle_node_matcher=matches_action(slam_toolbox),
            transition_id=Transition.TRANSITION_CONFIGURE,
        )
    )

    # Bước 2: Ngay khi chuyển sang trạng thái 'inactive' (configure xong), tự động gửi lệnh ACTIVATE
    activate_event = RegisterEventHandler(
        OnStateTransition(
            target_lifecycle_node=slam_toolbox,
            start_state='configuring',
            goal_state='inactive',
            entities=[
                EmitEvent(
                    event=ChangeState(
                        lifecycle_node_matcher=matches_action(slam_toolbox),
                        transition_id=Transition.TRANSITION_ACTIVATE,
                    )
                )
            ],
        )
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'slam_params_file',
            default_value=default_slam_params,
            description='File tham so SLAM Toolbox'
        ),
        slam_toolbox,
        configure_event,
        activate_event,
    ])

