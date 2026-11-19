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

## Launch

```bash
ros2 launch robot_competition competition.launch.py
```

For initial drive/TF validation without Nav2:

```bash
ros2 launch robot_competition competition.launch.py start_navigation:=false
```

Arguments: `gui:=true|false`, `start_navigation:=true|false`.

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
