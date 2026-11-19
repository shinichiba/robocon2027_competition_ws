#!/usr/bin/env python3
"""Staged launch for a two-robot Gazebo / ROS 2 Lyrical competition."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
    LogError,
    LogInfo,
    RegisterEventHandler,
    TimerAction,
    SetEnvironmentVariable,
)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit, OnProcessStart
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
    
def _color_to_rgba(color):
    """Convert a named color or 'r,g,b,a' string to an SDF RGBA value."""
    colors = {
        'blue': (0.1, 0.25, 0.9, 1.0),
        'red': (0.9, 0.1, 0.1, 1.0),
        'green': (0.1, 0.75, 0.2, 1.0),
        'yellow': (0.95, 0.8, 0.05, 1.0),
        'orange': (1.0, 0.35, 0.03, 1.0),
        'white': (0.9, 0.9, 0.9, 1.0),
        'black': (0.05, 0.05, 0.05, 1.0),
    }
    key = str(color).strip().lower()
    if key in colors:
        return colors[key]
    try:
        values = tuple(float(v.strip()) for v in key.split(','))
        if len(values) == 3:
            values = (*values, 1.0)
        if len(values) != 4 or any(v < 0.0 or v > 1.0 for v in values):
            raise ValueError
        return values
    except ValueError as exc:
        raise ValueError(
            "cube_color must be a named color or r,g,b[,a] values in [0,1]"
        ) from exc
def make_cube_grid(context):
    """
    Spawn a configurable grid of static 0.35 m cubes in Gazebo.

    cube_origin_x/y is the CENTER of the bottom-layer cube at grid index
    (0, 0), not the lower-left corner of the whole arrangement.
    """
    nx = int(LaunchConfiguration('cube_count_x').perform(context))
    ny = int(LaunchConfiguration('cube_count_y').perform(context))
    nz = int(LaunchConfiguration('cube_count_z').perform(context))
    size = float(LaunchConfiguration('cube_size').perform(context))
    size_sky = float(LaunchConfiguration('cube_sky_block_size').perform(context))
    gap = float(LaunchConfiguration('cube_gap').perform(context))
    origin_x = float(LaunchConfiguration('cube_origin_x').perform(context))
    origin_y = float(LaunchConfiguration('cube_origin_y').perform(context))
    origin_red_x = float(LaunchConfiguration('cube_red_origin_x').perform(context))
    origin_red_y = float(LaunchConfiguration('cube_red_origin_y').perform(context))
    color = _color_to_rgba(LaunchConfiguration('cube_color').perform(context))
    color_red = _color_to_rgba('red')
    color_yellow = _color_to_rgba('yellow')
    delay = float(LaunchConfiguration('cube_start_delay').perform(context))

    if min(nx, ny, nz) < 1 or size <= 0.0 or gap < 0.0 or delay < 0.0:
        raise ValueError('Cube counts and size must be positive; gap/delay cannot be negative.')

    rgba = ' '.join(f'{v:1.0f}' for v in color)
    rgba_red = ' '.join(f'{v:1.0f}' for v in color_red) 
    rgba_yellow = ' '.join(f'{v:1.0f}' for v in color_yellow) 
    spawns = []
    index = 0
    for iz in range(nz):
        for iy in range(ny):
            for ix in range(nx):
                index += 1
                name = f'cube_blue_{index:02d}'
                x = origin_x + ix * (size + gap)
                y = origin_y + iy * (size + gap)
                z = (iz + 0.5) * size
                sdf = f"""<?xml version="1.0"?>
<sdf version="1.9">
  <model name="{name}">
    <static>false</static>
    <pose>{x:.4f} {y:.4f} {z:.4f} 0 0 0</pose>
    <link name="cube">
      <inertial>
        <mass>0.6</mass>
        <inertia>
          <ixx>0.01225</ixx><iyy>0.01225</iyy><izz>0.01225</izz>
          <ixy>0</ixy><ixz>0</ixz><iyz>0</iyz>
        </inertia>
      </inertial>
      <collision name="collision">
        <geometry><box><size>{size:.4f} {size:.4f} {size:.4f}</size></box></geometry>
        <surface><friction><ode><mu>10.1</mu><mu2>10.1</mu2></ode></friction></surface>
      </collision>
      <visual name="visual">
        <geometry><box><size>{size:.4f} {size:.4f} {size:.4f}</size></box></geometry>
        <material><ambient>{rgba}</ambient><diffuse>{rgba}</diffuse></material>
      </visual>
    </link>
  </model>
</sdf>
"""
                # ros_gz_sim create may override the <pose> in the SDF
                # string with its default spawn pose (0, 0, 0). Pass the
                # calculated world pose explicitly for every cube.
                spawns.append(Node(
                    package='ros_gz_sim',
                    executable='create',
                    name=f'spawn_{name}',
                    arguments=[
                        '-string', sdf,
                        '-name', name,
                        '-x', f'{x:.4f}',
                        '-y', f'{y:.4f}',
                        '-z', f'{z:.4f}',
                        '-R', '0',
                        '-P', '0',
                        '-Y', '0',
                    ],
                    output='screen',
                ))
    # Spawn red earth block
    index = 0           
    for iz in range(nz):
        for iy in range(ny):
            for ix in range(nx):
                index += 1
                name = f'cube_red_{index:02d}'
                x = origin_red_x + ix * (size + gap)
                y = origin_red_y + iy * (size + gap)
                z = (iz + 0.5) * size
                sdf = f"""<?xml version="1.0"?>
<sdf version="1.9">
  <model name="{name}">
    <static>false</static>
    <pose>{x:.4f} {y:.4f} {z:.4f} 0 0 0</pose>
    <link name="cube">
      <inertial>
        <mass>0.6</mass>
        <inertia>
          <ixx>0.01225</ixx><iyy>0.01225</iyy><izz>0.01225</izz>
          <ixy>0</ixy><ixz>0</ixz><iyz>0</iyz>
        </inertia>
      </inertial>
      <collision name="collision">
        <geometry><box><size>{size:.4f} {size:.4f} {size:.4f}</size></box></geometry>
        <surface><friction><ode><mu>10.1</mu><mu2>10.1</mu2></ode></friction></surface>
      </collision>
      <visual name="visual">
        <geometry><box><size>{size:.4f} {size:.4f} {size:.4f}</size></box></geometry>
        <material><ambient>{rgba_red}</ambient><diffuse>{rgba_red}</diffuse></material>
      </visual>
    </link>
  </model>
</sdf>
"""
                # ros_gz_sim create may override the <pose> in the SDF
                # string with its default spawn pose (0, 0, 0). Pass the
                # calculated world pose explicitly for every cube.
                spawns.append(Node(
                    package='ros_gz_sim',
                    executable='create',
                    name=f'spawn_{name}',
                    arguments=[
                        '-string', sdf,
                        '-name', name,
                        '-x', f'{x:.4f}',
                        '-y', f'{y:.4f}',
                        '-z', f'{z:.4f}',
                        '-R', '0',
                        '-P', '0',
                        '-Y', '0',
                    ],
                    output='screen',
                ))

    footprint_x = nx * size + max(0, nx - 1) * gap
    footprint_y = ny * size + max(0, ny - 1) * gap
    footprint_z = nz * size
    print(
        f'[cube_grid] Spawning {index} cubes; footprint '
        f'{footprint_x:.2f} x {footprint_y:.2f} x {footprint_z:.2f} m; '
        f'first cube center=({origin_x:.2f}, {origin_y:.2f}).'
    )
    # Spawn skyblock
    index = 0 
    sky_nx = int(3)
    sky_ny = int(3)
    sky_nz = int(1)
    sky_gap = float(0.2)
    for iz in range(sky_nz):
        for iy in range(sky_ny):
            for ix in range(sky_nx):
                index += 1
                name = f'cube_sky_{index:02d}'
                x = -0.6 + ix * (size_sky + sky_gap)
                y = -4.6 + iy * (size_sky + sky_gap)
                z = (iz + 0.5) * size_sky
                sdf = f"""<?xml version="1.0"?>
<sdf version="1.9">
  <model name="{name}">
    <static>false</static>
    <pose>{x:.4f} {y:.4f} {z:.4f} 0 0 0</pose>
    <link name="cube">
      <inertial>
        <mass>0.22</mass>
        <inertia>
          <ixx>0.01225</ixx><iyy>0.01225</iyy><izz>0.01225</izz>
          <ixy>0</ixy><ixz>0</ixz><iyz>0</iyz>
        </inertia>
      </inertial>
      <collision name="collision">
        <geometry><box><size>{size_sky:.4f} {size_sky:.4f} {size_sky:.4f}</size></box></geometry>
        <surface><friction><ode><mu>10.1</mu><mu2>10.1</mu2></ode></friction></surface>
      </collision>
      <visual name="visual">
        <geometry><box><size>{size_sky:.4f} {size_sky:.4f} {size_sky:.4f}</size></box></geometry>
        <material><ambient>{rgba_yellow}</ambient><diffuse>{rgba_yellow}</diffuse></material>
      </visual>
    </link>
  </model>
</sdf>
"""
                # ros_gz_sim create may override the <pose> in the SDF
                # string with its default spawn pose (0, 0, 0). Pass the
                # calculated world pose explicitly for every cube.
                spawns.append(Node(
                    package='ros_gz_sim',
                    executable='create',
                    name=f'spawn_{name}',
                    arguments=[
                        '-string', sdf,
                        '-name', name,
                        '-x', f'{x:.4f}',
                        '-y', f'{y:.4f}',
                        '-z', f'{z:.4f}',
                        '-R', '0',
                        '-P', '0',
                        '-Y', '0',
                    ],
                    output='screen',
                ))

    footprint_x = nx * size + max(0, nx - 1) * gap
    footprint_y = ny * size + max(0, ny - 1) * gap
    footprint_z = nz * size
    print(
        f'[cube_grid] Spawning {index} cubes; footprint '
        f'{footprint_x:.2f} x {footprint_y:.2f} x {footprint_z:.2f} m; '
        f'first cube center=({origin_x:.2f}, {origin_y:.2f}).'
    )
    # Stagger create requests so Gazebo receives them one at a time.
    return [TimerAction(
        period=delay,
        actions=[
            TimerAction(period=i * 0.25, actions=[spawn])
            for i, spawn in enumerate(spawns)
        ],
    )]


def generate_launch_description():
    package_share = get_package_share_directory('robocon2027_competition_simulator')
    world_file = os.path.join(
        package_share, 'worlds', 'robocon2027_arena.sdf'
    )
    # =========================================================
    # set_env_action
    # =========================================================
    # 1. Định nghĩa đường dẫn tới thư mục models của bạn
    # Sử dụng os.path.expanduser('~') để thay thế cho dấu '~' trong Python
    models_path = os.path.join(package_share, 'models')

    # Nếu hệ thống đã có sẵn biến GZ_SIM_RESOURCE_PATH, ta sẽ cộng chuỗi nối tiếp nó
    current_gz_path = os.environ.get('GZ_SIM_RESOURCE_PATH', '')
    if current_gz_path:
        full_gz_path = f"{models_path}:{current_gz_path}"
    else:
        full_gz_path = models_path

    # 2. Tạo hành động cấu hình biến môi trường cho Gazebo
    set_env_action = SetEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH', 
        value=full_gz_path
    )
    
    robot1 = make_robot(
        'robot1', -5.0, -5.0, 0.0,
        LaunchConfiguration('robot1_color'), package_share,
    )
    robot2 = make_robot(
        'robot2', 4.5, -5.0, 0.0,
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
    # Separate cube-grid generator; it starts after Gazebo and clock_bridge.
    cube_grid = RegisterEventHandler(OnProcessStart(
        target_action=clock_bridge,
        on_start=OpaqueFunction(function=make_cube_grid),
    ))
    competition_manager = Node(
        package='robocon2027_competition_simulator',
        executable='competition_manager',
        name='competition_manager',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'match_duration_sec': 180.0,
        }],
    )
    odom_tf_splitter = Node(
    package='robocon2027_competition_simulator',
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
        package='robocon2027_competition_simulator',
        executable='tf_aggregator',
        name='tf_aggregator',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            # Visualization-only anchors: map frames are placed at the
            # corresponding initial Gazebo spawn poses.
            'robot1_map_x': -5.0,
            'robot1_map_y': -5.0,
            'robot1_map_yaw': 0.0,
            'robot2_map_x': 4.5,
            'robot2_map_y': -5.0,
            'robot2_map_yaw': 0.0,
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
            default_value='false',
            description='Start SLAM Toolbox'
        ),
        DeclareLaunchArgument(
            'start_navigation', default_value='false',
            description='Start SLAM Toolbox and Nav2 after both robots are ready',
        ),
        DeclareLaunchArgument(
            'robot1_color', default_value='red',
            description='Robot 1 body color',
        ),
        DeclareLaunchArgument(
            'robot2_color', default_value='blue',
            description='Robot 2 body color',
        ),
        DeclareLaunchArgument('cube_count_x', default_value='2',
                              description='Number of cubes along X'),
        DeclareLaunchArgument('cube_count_y', default_value='1',
                              description='Number of cubes along Y'),
        DeclareLaunchArgument('cube_count_z', default_value='2',
                              description='Number of cube layers along Z'),
        DeclareLaunchArgument('cube_origin_x', default_value='3.0',
                              description='X center of the first bottom cube (m)'),
        DeclareLaunchArgument('cube_origin_y', default_value='4.5',
                              description='Y center of the first bottom cube (m)'),
        DeclareLaunchArgument('cube_red_origin_x', default_value='-4.9',
                              description='X center of the first bottom cube (m)'),
        DeclareLaunchArgument('cube_red_origin_y', default_value='4.5',
                              description='Y center of the first bottom cube (m)'),
        DeclareLaunchArgument('cube_size', default_value='0.35',
                              description='Cube edge length (m)'),
        DeclareLaunchArgument('cube_sky_block_size', default_value='0.20',
                              description='cube_sky_block_size edge length (m)'),                    
        DeclareLaunchArgument('cube_gap', default_value='0.10',
                              description='Gap between neighboring cubes (m)'),     
        DeclareLaunchArgument('cube_color', default_value='blue',
                              description='Cube color: blue/red/green/yellow/orange/white/black or r,g,b[,a]'),
        DeclareLaunchArgument('cube_start_delay', default_value='5.0',
                              description='Seconds to wait after launch actions before spawning cubes'),
        set_env_action,
        gazebo,
        clock_bridge,
        cube_grid,
        robot1['state_publisher'],
        robot2['state_publisher'],
        # Give robot_state_publisher time to publish robot_description before spawn.
        TimerAction(
            period=3.0,
            actions=[robot1['spawn'], robot2['spawn']],
        ),
        *event_handlers,
    ])
