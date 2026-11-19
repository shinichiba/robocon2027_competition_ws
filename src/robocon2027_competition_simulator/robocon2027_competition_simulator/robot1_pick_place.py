#!/usr/bin/env python3
"""
Autonomous one-block pick-and-place for robot1 (ROS 2 Lyrical + Nav2).

IMPORTANT:
- Uses Nav2 NavigateToPose and ros2_control ForwardCommandController topics.
- Reads /robot1/joint_states to verify that lift/fingers reached commanded positions.
- Joint position alone does NOT prove that a cube is physically held. For reliable
  grasp confirmation, publish std_msgs/Bool on grasp_state_topic from a Gazebo
  contact sensor / attachment detector and set require_grasp_sensor:=true.
- Default coordinates are assumptions for the competition arena described in the
  accompanying instructions. Tune them to the actual spawned cube and platform.
"""

import math
from enum import Enum, auto

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.duration import Duration

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from nav2_msgs.action import NavigateToPose
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray, Bool


class Phase(Enum):
    WAIT_READY = auto()
    INIT_POSE = auto()
    NAV_PICK = auto()
    OPEN_PICK = auto()
    LOWER_PICK = auto()
    CLOSE_GRIPPER = auto()
    VERIFY_GRASP = auto()
    LIFT_CARRY = auto()
    NAV_PLACE = auto()
    LOWER_PLACE = auto()
    RELEASE = auto()
    LIFT_CLEAR = auto()
    NAV_RETREAT = auto()
    DONE = auto()
    FAILED = auto()


class Robot1PickPlace(Node):
    def __init__(self):
        super().__init__('robot1_pick_place')

        # Robot / navigation
        self.declare_parameter('robot_ns', 'robot1')
        self.declare_parameter('map_frame', 'robot1/map')
        self.declare_parameter('nav_action', '/robot1/navigate_to_pose')
        self.declare_parameter('initialpose_topic', '/robot1/initialpose')
        self.declare_parameter('joint_states_topic', '/robot1/joint_states')
        self.declare_parameter('lift_topic',
                               '/robot1/lift_position_controller/commands')
        self.declare_parameter('gripper_topic',
                               '/robot1/gripper_position_controller/commands')
        # Initial pose assumptions (điều chỉnh cho khớp với vị trí spawn của robot1)
        self.declare_parameter('send_init_pose', True)
        self.declare_parameter('init_x', -4.5)
        self.declare_parameter('init_y', -4.5)
        self.declare_parameter('init_yaw', 0.0)
        self.declare_parameter('init_pose_wait_sec', 5.0)
        
        # Pose assumptions: cube_r1_01 near (-3.7, -3.7), platform at (0, 0).
        # Robot faces +X at pickup/place; the gripper is mounted at the front.
        self.declare_parameter('pickup_x', -1.5)
        self.declare_parameter('pickup_y', -4.0)
        self.declare_parameter('pickup_yaw', 0.0)
        self.declare_parameter('place_x', -3.5)
        self.declare_parameter('place_y', 4.0)
        self.declare_parameter('place_yaw', 0.0)
        self.declare_parameter('retreat_x', -1.0)
        self.declare_parameter('retreat_y', 4.2)
        self.declare_parameter('retreat_yaw', 0.0)

        # Controller setpoints (metres/radians as applicable)
        self.declare_parameter('lift_pick', 0.0)
        self.declare_parameter('lift_carry', 0.30)
        self.declare_parameter('lift_place', 0.0)
        self.declare_parameter('lift_clear', 0.30)
        self.declare_parameter('gripper_open', -0.08)
        self.declare_parameter('gripper_close', 0.08)
        self.declare_parameter('joint_tolerance', 0.015)
        self.declare_parameter('joint_timeout_sec', 8.0)
        self.declare_parameter('phase_pause_sec', 1.0)
        self.declare_parameter('nav_server_timeout_sec', 30.0)
        self.declare_parameter('nav_result_timeout_sec', 180.0)

        # Optional real grasp confirmation.
        self.declare_parameter('grasp_state_topic', '')
        self.declare_parameter('require_grasp_sensor', False)
        self.declare_parameter('grasp_sensor_timeout_sec', 5.0)

        self.robot_ns = str(self.get_parameter('robot_ns').value)
        self.map_frame = str(self.get_parameter('map_frame').value)
        self.nav_action_name = str(self.get_parameter('nav_action').value)
        self.initialpose_topic = str(
            self.get_parameter('initialpose_topic').value)
            
        self.joint_states_topic = str(
            self.get_parameter('joint_states_topic').value)
        self.lift_topic = str(self.get_parameter('lift_topic').value)
        self.gripper_topic = str(self.get_parameter('gripper_topic').value)
        self.init_pose_pub = self.create_publisher(
            PoseWithCovarianceStamped, self.initialpose_topic, 10)
        self.lift_pub = self.create_publisher(
            Float64MultiArray, self.lift_topic, 10)
        self.gripper_pub = self.create_publisher(
            Float64MultiArray, self.gripper_topic, 10)

        self.joint_sub = self.create_subscription(
            JointState, self.joint_states_topic, self.joint_state_cb, 20)

        self.grasp_state_topic = str(
            self.get_parameter('grasp_state_topic').value).strip()
        self.require_grasp_sensor = bool(
            self.get_parameter('require_grasp_sensor').value)
        self.grasp_sensor_value = None
        self.grasp_sub = None
        if self.grasp_state_topic:
            self.grasp_sub = self.create_subscription(
                Bool, self.grasp_state_topic, self.grasp_state_cb, 10)
        elif self.require_grasp_sensor:
            raise RuntimeError(
                'require_grasp_sensor=true nhưng grasp_state_topic đang rỗng.')

        self.nav_client = ActionClient(
            self, NavigateToPose, self.nav_action_name)

        self.joint_positions = {}
        self.joint_velocities = {}
        self.phase = Phase.WAIT_READY
        self.phase_started = self.now_sec()
        self.phase_deadline = None
        self.nav_goal_active = False
        self.nav_goal_done = False
        self.nav_goal_ok = False
        self.nav_goal_handle = None
        self.nav_result_deadline = None
        self.target_joint = None
        self.target_joint_value = None
        self.last_command_time = 0.0
        self.grasp_verified = False
        self.started = False

        self.timer = self.create_timer(0.10, self.control_loop)
        self.get_logger().info(
            'Robot1 pick-and-place node đã khởi động. Chờ Nav2, controller và joint_states...')

    def now_sec(self):
        return self.get_clock().now().nanoseconds / 1e9

    def joint_state_cb(self, msg: JointState):
        for i, name in enumerate(msg.name):
            if i < len(msg.position):
                self.joint_positions[name] = float(msg.position[i])
            if i < len(msg.velocity):
                self.joint_velocities[name] = float(msg.velocity[i])

    def grasp_state_cb(self, msg: Bool):
        self.grasp_sensor_value = bool(msg.data)

    def full_joint_name(self, short_name):
        return f'{self.robot_ns}/{short_name}'

    def enter(self, phase: Phase, timeout=None):
        self.phase = phase
        self.phase_started = self.now_sec()
        self.phase_deadline = (
            self.phase_started + float(timeout) if timeout is not None else None)
        self.target_joint = None
        self.target_joint_value = None
        self.get_logger().info(f'==> {phase.name}')
    def publish_initial_pose(self):
        x = float(self.get_parameter('init_x').value)
        y = float(self.get_parameter('init_y').value)
        yaw = float(self.get_parameter('init_yaw').value)

        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = self.map_frame
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.pose.pose.position.x = x
        msg.pose.pose.position.y = y
        msg.pose.pose.position.z = 0.0
        msg.pose.pose.orientation.z = math.sin(yaw / 2.0)
        msg.pose.pose.orientation.w = math.cos(yaw / 2.0)

        # Ma trận hiệp phương sai (covariance 6x6): đặt độ tin cậy cao cho x, y, yaw
        cov = [0.0] * 36
        cov[0] = 0.05   # Phương sai trục X (m^2)
        cov[7] = 0.05   # Phương sai trục Y (m^2)
        cov[35] = 0.03  # Phương sai góc Yaw (rad^2)
        msg.pose.covariance = cov

        self.init_pose_pub.publish(msg)
    def publish_lift(self, value):
        msg = Float64MultiArray()
        msg.data = [float(value)]
        self.lift_pub.publish(msg)

    def publish_gripper(self, value):
        # URDF has two finger joints; their axes are mirrored. With the current
        # Xacro, equal positive joint positions move both fingers inward.
        msg = Float64MultiArray()
        msg.data = [float(value), float(value)]
        self.gripper_pub.publish(msg)

    def command_until_reached(self, kind, value, joint_names):
        """Republish command and wait until joint_states reaches target."""
        now = self.now_sec()
        if now - self.last_command_time >= 0.20:
            if kind == 'lift':
                self.publish_lift(value)
            else:
                self.publish_gripper(value)
            self.last_command_time = now

        if not all(name in self.joint_positions for name in joint_names):
            return False

        tol = float(self.get_parameter('joint_tolerance').value)
        return all(abs(self.joint_positions[name] - value) <= tol
                   for name in joint_names)

    def send_nav_goal(self, x, y, yaw, next_phase):
        if not self.nav_client.server_is_ready():
            if not self.nav_client.wait_for_server(timeout_sec=0.0):
                return False

        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = self.map_frame
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(x)
        goal.pose.pose.position.y = float(y)
        goal.pose.pose.position.z = 0.0
        goal.pose.pose.orientation.z = math.sin(float(yaw) / 2.0)
        goal.pose.pose.orientation.w = math.cos(float(yaw) / 2.0)

        self.nav_goal_active = True
        self.nav_goal_done = False
        self.nav_goal_ok = False
        self.enter(next_phase, float(
            self.get_parameter('nav_result_timeout_sec').value))
        self.get_logger().info(
            f'Nav2 goal: x={x:.2f}, y={y:.2f}, yaw={yaw:.2f}, frame={self.map_frame}')

        future = self.nav_client.send_goal_async(goal)
        future.add_done_callback(self.nav_goal_response_cb)
        return True

    def nav_goal_response_cb(self, future):
        try:
            self.nav_goal_handle = future.result()
            if self.nav_goal_handle is None or not self.nav_goal_handle.accepted:
                self.get_logger().error('Nav2 từ chối goal.')
                self.nav_goal_done = True
                self.nav_goal_ok = False
                return
            result_future = self.nav_goal_handle.get_result_async()
            result_future.add_done_callback(self.nav_result_cb)
        except Exception as exc:
            self.get_logger().error(f'Lỗi gửi Nav2 goal: {exc}')
            self.nav_goal_done = True
            self.nav_goal_ok = False

    def nav_result_cb(self, future):
        try:
            result = future.result()
            self.nav_goal_ok = (result.status == GoalStatus.STATUS_SUCCEEDED)
            self.nav_goal_done = True
            if self.nav_goal_ok:
                self.get_logger().info('Nav2: đã tới waypoint.')
            else:
                self.get_logger().error(
                    f'Nav2 thất bại, status={result.status}.')
        except Exception as exc:
            self.get_logger().error(f'Lỗi nhận kết quả Nav2: {exc}')
            self.nav_goal_done = True
            self.nav_goal_ok = False

    def fail(self, reason):
        self.get_logger().error(f'PICK-PLACE DỪNG: {reason}')
        self.enter(Phase.FAILED)

    def timed_out(self):
        return (self.phase_deadline is not None and
                self.now_sec() > self.phase_deadline)

    def control_loop(self):
        if self.phase in (Phase.DONE, Phase.FAILED):
            return

        now = self.now_sec()
        pause = float(self.get_parameter('phase_pause_sec').value)
        joint_timeout = float(
            self.get_parameter('joint_timeout_sec').value)

        if self.phase == Phase.WAIT_READY:
            joints_ready = (
                self.full_joint_name('lift_joint') in self.joint_positions and
                self.full_joint_name('left_finger_joint') in self.joint_positions and
                self.full_joint_name('right_finger_joint') in self.joint_positions
            )
            if not joints_ready:
                return
            if not self.nav_client.wait_for_server(timeout_sec=0.0):
                self.get_logger().info(
                    f'Đang chờ Nav2 action {self.nav_action_name}...', throttle_duration_sec=5.0)
                return
            self.started = True
            if bool(self.get_parameter('send_init_pose').value):
                self.enter(Phase.INIT_POSE)
                self.publish_initial_pose()
                self.last_init_pose_time = now
                self.get_logger().info(
                f"Đã gửi initial pose tới {self.initialpose_topic}: "
                f"x={self.get_parameter('init_x').value:.2f}, "
                f"y={self.get_parameter('init_y').value:.2f}, "
                f"yaw={self.get_parameter('init_yaw').value:.2f}")
            else:
                self.enter(Phase.NAV_PICK)
                self.send_nav_goal(
                self.get_parameter('pickup_x').value,
                self.get_parameter('pickup_y').value,
                self.get_parameter('pickup_yaw').value,
                Phase.NAV_PICK)
            return
        if self.phase == Phase.INIT_POSE:
            # Gửi lặp lại mỗi 0.5s trong thời gian chờ để đảm bảo AMCL/SLAM nhận được
            if now - self.last_init_pose_time >= 0.50:
                self.publish_initial_pose()
                self.last_init_pose_time = now
                wait_sec = float(self.get_parameter('init_pose_wait_sec').value)
                if now - self.phase_started >= wait_sec:
                    self.enter(Phase.NAV_PICK)
                    self.send_nav_goal(
                    self.get_parameter('pickup_x').value,
                    self.get_parameter('pickup_y').value,
                    self.get_parameter('pickup_yaw').value,
                    Phase.NAV_PICK)
                return
        if self.phase in (Phase.NAV_PICK, Phase.NAV_PLACE, Phase.NAV_RETREAT):
            if self.nav_goal_done:
                self.nav_goal_active = False
                if not self.nav_goal_ok:
                    self.fail(f'Nav2 không tới được waypoint {self.phase.name}.')
                    return
                if self.phase == Phase.NAV_PICK:
                    self.enter(Phase.OPEN_PICK, joint_timeout)
                elif self.phase == Phase.NAV_PLACE:
                    self.enter(Phase.LOWER_PLACE, joint_timeout)
                else:
                    self.enter(Phase.DONE)
                    self.get_logger().info(
                        'HOÀN TẤT: đã thực hiện chu trình gắp, đặt và lùi khỏi bục.')
                return
            if self.timed_out():
                if self.nav_goal_handle is not None:
                    self.nav_goal_handle.cancel_goal_async()
                self.fail('Nav2 quá thời gian chờ.')
            return

        if self.phase == Phase.OPEN_PICK:
            ok = self.command_until_reached(
                'gripper', self.get_parameter('gripper_open').value,
                [self.full_joint_name('left_finger_joint'),
                 self.full_joint_name('right_finger_joint')])
            if ok and now - self.phase_started >= pause:
                self.enter(Phase.LOWER_PICK, joint_timeout)
            elif self.timed_out():
                self.fail('Không mở được tay gắp; kiểm tra gripper controller/joint_states.')
            return

        if self.phase == Phase.LOWER_PICK:
            ok = self.command_until_reached(
                'lift', self.get_parameter('lift_pick').value,
                [self.full_joint_name('lift_joint')])
            if ok and now - self.phase_started >= pause:
                self.enter(Phase.CLOSE_GRIPPER, joint_timeout)
            elif self.timed_out():
                self.fail('Không hạ được lift đến vị trí gắp.')
            return

        if self.phase == Phase.CLOSE_GRIPPER:
            ok = self.command_until_reached(
                'gripper', self.get_parameter('gripper_close').value,
                [self.full_joint_name('left_finger_joint'),
                 self.full_joint_name('right_finger_joint')])
            if ok and now - self.phase_started >= pause:
                self.grasp_sensor_value = (
                    self.grasp_sensor_value if self.grasp_sub else None)
                self.enter(Phase.VERIFY_GRASP,
                           float(self.get_parameter('grasp_sensor_timeout_sec').value))
            elif self.timed_out():
                self.fail('Không đóng được tay gắp đến vị trí đặt.')
            return

        if self.phase == Phase.VERIFY_GRASP:
            if self.grasp_sub is not None:
                if self.grasp_sensor_value is True:
                    self.grasp_verified = True
                elif self.grasp_sensor_value is False and self.require_grasp_sensor:
                    if self.timed_out():
                        self.fail('Cảm biến báo không giữ được vật.')
                        return
                    return
                elif self.timed_out() and self.require_grasp_sensor:
                    self.fail('Không nhận được xác nhận gắp từ cảm biến.')
                    return
                elif self.grasp_sensor_value is None:
                    return
            else:
                # No contact/attachment sensor exists in the supplied Xacro.
                # This only confirms finger motion, not that the cube is held.
                self.grasp_verified = False
                self.get_logger().warning(
                    'Chưa có cảm biến xác nhận vật. Chỉ xác nhận ngón tay đã đóng; '
                    'hãy quan sát Gazebo để chắc chắn khối không rơi.')
            self.enter(Phase.LIFT_CARRY, joint_timeout)
            return

        if self.phase == Phase.LIFT_CARRY:
            ok = self.command_until_reached(
                'lift', self.get_parameter('lift_carry').value,
                [self.full_joint_name('lift_joint')])
            if ok and now - self.phase_started >= pause:
                self.enter(Phase.NAV_PLACE)
                self.send_nav_goal(
                    self.get_parameter('place_x').value,
                    self.get_parameter('place_y').value,
                    self.get_parameter('place_yaw').value,
                    Phase.NAV_PLACE)
            elif self.timed_out():
                self.fail('Không nâng được khối lên độ cao mang.')
            return

        if self.phase == Phase.LOWER_PLACE:
            ok = self.command_until_reached(
                'lift', self.get_parameter('lift_place').value,
                [self.full_joint_name('lift_joint')])
            if ok and now - self.phase_started >= pause:
                self.enter(Phase.RELEASE, joint_timeout)
            elif self.timed_out():
                self.fail('Không hạ được khối xuống bục.')
            return

        if self.phase == Phase.RELEASE:
            ok = self.command_until_reached(
                'gripper', self.get_parameter('gripper_open').value,
                [self.full_joint_name('left_finger_joint'),
                 self.full_joint_name('right_finger_joint')])
            if ok and now - self.phase_started >= pause:
                self.enter(Phase.LIFT_CLEAR, joint_timeout)
            elif self.timed_out():
                self.fail('Không mở được tay gắp để thả khối.')
            return

        if self.phase == Phase.LIFT_CLEAR:
            ok = self.command_until_reached(
                'lift', self.get_parameter('lift_clear').value,
                [self.full_joint_name('lift_joint')])
            if ok and now - self.phase_started >= pause:
                self.enter(Phase.NAV_RETREAT)
                self.send_nav_goal(
                    self.get_parameter('retreat_x').value,
                    self.get_parameter('retreat_y').value,
                    self.get_parameter('retreat_yaw').value,
                    Phase.NAV_RETREAT)
            elif self.timed_out():
                self.fail('Không nâng lift lên vị trí an toàn sau khi thả.')
            return


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = Robot1PickPlace()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        if node is not None:
            node.get_logger().fatal(str(exc))
        else:
            print(f'Không thể khởi tạo robot1_pick_place: {exc}')
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
