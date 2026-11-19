<img width="1818" height="970" alt="image" src="https://github.com/user-attachments/assets/1b4324a2-b4d9-446e-ab46-2c50d7c244ee" />

# Two-robot competition simulation — ROS 2 Lyrical / Gazebo Sim Jetty

Reference workspace for an 11 m × 11 m arena, two 600 mm skid-steer robots,
350 mm cubic blocks (0.6 kg), physical two-finger grippers, separate SLAM
Toolbox/Nav2 stacks, and a competition timer/scoreboard.

## Assumptions that must be checked against the official field
- Cubes are 350 × 350 × 350 mm and 0.6 kg.
- The robot has a separate 1 m × 1 m start pad at each corner; its five cubes are in an adjacent 0.8 m × 0.8 m pickup zone. Robot 1's pickup cluster is centred near (-3.5, -3.5) m and robot 2's near (3.5, 3.5) m. Four cubes are on the floor (2 × 2) and a fifth is stacked on one of them. Five cubes cannot all fit side-by-side.
- The 500 × 500 mm centre platform is the stacking target.
- Four ordinary driven wheels are configured as skid-steer (left pair/right
  pair), not mecanum.
- Grasping is physical: finger collisions, contact and friction; no fixed-joint
  attach/detach trick is used.
- This is a source baseline, not a binary-tested deployment. Verify package
  names, plugin loading, TF, topic remappings and contact behavior on the
  actual ROS Lyrical + Jetty installation.

## Install (Ubuntu 26.04 / ROS 2 Lyrical / Gazebo Jetty)

```bash
sudo apt update
sudo apt install -y \
  ros-lyrical-ros-gz-sim ros-lyrical-ros-gz-bridge \
  ros-lyrical-gz-ros2-control ros-lyrical-ros2-controllers \
  ros-lyrical-xacro ros-lyrical-robot-state-publisher \
  ros-lyrical-slam-toolbox ros-lyrical-navigation2 \
  ros-lyrical-nav2-bringup ros-lyrical-rviz2 \
  ros-lyrical-tf2-tools python3-colcon-common-extensions
```

If an apt package name differs in the Lyrical repository snapshot, locate it
with `apt-cache search ros-lyrical-`.

## Build

```bash
source /opt/ros/lyrical/setup.bash
mkdir -p ~/robot_competition_ws/src
# Extract/copy this workspace so its src/ directory is ~/robot_competition_ws/src
cd ~/robot_competition_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

## Xây dựng và lưu bản đồ (SLAM)

Thực hiện lần lượt các bước dưới đây trong **4 terminal riêng biệt**. Giữ các terminal đang chạy cho đến khi hoàn tất quá trình tạo bản đồ.

**Terminal 1 – Khởi động mô phỏng**

```bash
ros2 launch robocon2027_competition_simulator competition.launch.py start_slam:=false start_navigation:=false
```

**Terminal 2 – Khởi động SLAM cho robot1**

```bash
ros2 launch robocon2027_competition_simulator mapping_robot1.launch.py
```

**Terminal 3 – Mở RViz2**

```bash
ros2 launch robocon2027_competition_simulator rviz_robot1.launch.py
```

**Terminal 4 – Điều khiển robot bằng bàn phím**

```bash
ros2 run robocon2027_competition_simulator 1keyboard_control
```

Sử dụng bàn phím để điều khiển robot di chuyển qua các khu vực của sân thi đấu. Theo dõi bản đồ được cập nhật trên RViz2 và bảo đảm robot đã quét đủ khu vực cần thiết.

### Lưu bản đồ

Sau khi hoàn tất quá trình xây dựng bản đồ, mở một terminal mới và chạy:

```bash
ros2 run nav2_map_server map_saver_cli \
  -t /robot1/map \
  -f robot1_map
```

Lệnh trên lưu bản đồ với tên `robot1_map` tại thư mục làm việc hiện tại (thường tạo ra hai tệp `robot1_map.yaml` và `robot1_map.pgm`).

## Chạy điều hướng bằng bản đồ đã lưu (Nav2)

Sau khi đã tạo và lưu bản đồ, thực hiện lần lượt các bước dưới đây. Mở **5 terminal riêng biệt** và giữ các tiến trình đang chạy.

**Terminal 1 – Khởi động mô phỏng, tắt SLAM và Navigation mặc định**

```bash
ros2 launch robocon2027_competition_simulator competition.launch.py start_slam:=false start_navigation:=false
```

**Terminal 2 – Khởi động Navigation cho robot1**

```bash
ros2 launch robocon2027_competition_simulator navigation_robot1.launch.py
```

**Terminal 3 – Mở RViz2**

```bash
ros2 launch robocon2027_competition_simulator rviz_robot1.launch.py
```

**Terminal 4 – Điều khiển robot bằng bàn phím (nếu cần)**

```bash
ros2 run robocon2027_competition_simulator 1keyboard_control
```

**Terminal 5 – Chạy chương trình gắp và đặt vật**

```bash
ros2 run robocon2027_competition_simulator robot1_pick_place
```

Trong RViz2, kiểm tra bản đồ và các khung tọa độ của robot. Sử dụng công cụ **2D Goal Pose** để gửi mục tiêu điều hướng nếu cần. Chương trình `robot1_pick_place` thực hiện quy trình gắp và đặt vật theo logic đã được cài đặt trong package.

> **Lưu ý:** Phần điều hướng sử dụng bản đồ đã lưu cần được cấu hình để `navigation_robot1.launch.py` nạp đúng tệp `robot1_map.yaml`. Đặt tệp bản đồ tại đúng vị trí mà launch file đang tham chiếu, hoặc cập nhật đường dẫn trong cấu hình Navigation. Nếu bản đồ không hiển thị trong RViz2, kiểm tra lại đường dẫn bản đồ, topic `/robot1/map` và các khung TF.

## Validate

```bash
ros2 node list
ros2 topic list | grep -E 'robot1|robot2|clock'
ros2 topic echo /robot1/scan
ros2 topic echo /robot2/scan
ros2 control list_controllers -c /robot1/controller_manager
ros2 control list_controllers -c /robot2/controller_manager
ros2 run tf2_ros tf2_echo robot1/odom robot1/base_link
ros2 run tf2_ros tf2_echo robot2/odom robot2/base_link
```

Drive test (TwistStamped):

```bash
ros2 topic pub --rate 10 /robot1/diff_drive_controller/cmd_vel \
  geometry_msgs/msg/TwistStamped \
  "{header: {stamp: {sec: 0, nanosec: 0}}, twist: {linear: {x: 0.15}, angular: {z: 0.0}}}"
```

Lift and gripper commands:

```bash
ros2 topic pub --once /robot1/lift_position_controller/commands \
  std_msgs/msg/Float64MultiArray "{data: [0.20]}"
ros2 topic pub --once /robot1/gripper_position_controller/commands \
  std_msgs/msg/Float64MultiArray "{data: [0.15, 0.15]}"
```

The gripper coordinate is per finger: 0.0 is open and approximately 0.0825 m
is closed for the nominal 350 mm cube geometry. Verify axes and contact before
grasp tests.

## Competition manager

```bash
ros2 service call /competition/start std_srvs/srv/Trigger "{}"
ros2 service call /competition/stop std_srvs/srv/Trigger "{}"
```

After independently verifying that a cube has been stably stacked, a strategy
may report its unique ID:

```bash
ros2 topic pub --once /competition/robot1/placed_block std_msgs/msg/String "{data: 'cube_r1_01'}"
ros2 topic pub --once /competition/robot2/placed_block std_msgs/msg/String "{data: 'cube_r2_01'}"
ros2 topic echo /competition/scoreboard
```

The starter scoreboard trusts these event reports; it does not yet inspect
Gazebo object poses or contacts. For official judging, implement a referee
plugin/state estimator that verifies cube position, height, stability and ID.

## Physical-grasp calibration

1. Verify finger joint axes, collision geometry and opening direction.
2. Tune cube/finger friction for the actual materials.
3. Increase finger effort gradually; avoid starting with high forces.
4. Test one cube at low lift speed and low robot acceleration.
5. Check slip while driving and turning.
6. Tune contact solver iterations and simulation step size if contact jitters.
7. Do not report a grasp/stack as successful just because a command was sent.

## Important limitations

- A 2D LiDAR only sees the cube at its scan height; it does not provide a
  reliable 3D grasp pose. Use a camera/vision node or known arena coordinates
  for final grasp alignment.
- Nav2 parameters are starting values. Calibrate the footprint, costmaps,
  velocity limits, scan source and TF on the real URDF.
- Dynamic opponent avoidance needs additional tuning; the obstacle layer is
  only a baseline.
- Skid-steer odometry is affected by wheel scrub. Measure effective wheel
  separation/radius on the actual simulated chassis.
- The launch and plugins must be validated on the exact Lyrical/Jetty package
  snapshot before treating the workspace as competition-ready.
