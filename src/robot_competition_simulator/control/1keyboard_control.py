
#!/usr/bin/env python3
import sys
import os
import select
import termios
import tty
import threading

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import TwistStamped
from std_msgs.msg import Float64MultiArray


HELP = """
================ ROBOT TELEOP =================

  W / S : Tiến / Lùi
  A / D : Quay trái / Quay phải
  SPACE : Dừng đế robot

  I / K : Nâng / Hạ tay nâng
  J / L : Mở rộng / Đóng tay gắp

  Q / Z : Tăng / giảm vận tốc tuyến tính
  E / C : Tăng / giảm vận tốc góc

  Ctrl+C / Ctrl+Z / ESC : Thoát chương trình

================================================
Lưu ý:
- Đế robot tiếp tục di chuyển cho đến khi đổi lệnh
  hoặc nhấn SPACE.
- Khi thoát, chương trình gửi lệnh dừng đế robot.
================================================
"""


class RobotTeleop(Node):

    def __init__(self):
        super().__init__('robot_teleop')

        # Publishers
        self.cmd_vel_pub = self.create_publisher(
            TwistStamped,
            '/robot1/diff_drive_controller/cmd_vel',
            10
        )

        self.lift_pub = self.create_publisher(
            Float64MultiArray,
            '/robot1/lift_position_controller/commands',
            10
        )

        self.gripper_pub = self.create_publisher(
            Float64MultiArray,
            '/robot1/gripper_position_controller/commands',
            10
        )

        # Linear/angular velocity
        self.linear_speed = 1.00       # m/s
        self.angular_speed = 0.80      # rad/s

        # Speed adjustment (set max values to match controllers.yaml)
        self.linear_speed_step = 0.10  # m/s per key press
        self.angular_speed_step = 0.10 # rad/s per key press
        self.max_linear_speed = 3.00   # m/s
        self.max_angular_speed = 4.00  # rad/s

        # Lift joint limits (edit to match your URDF)
        self.lift_min = -0.50          # m
        self.lift_max = 0.50           # m
        self.lift_step = 0.02          # m
        self.lift_position = 0.00

        # Gripper limits (edit to match your URDF)
        self.gripper_min = 0.01        # m or rad
        self.gripper_max = 0.085        # m or rad
        self.gripper_step = 0.02
        self.gripper_position = 0.10   # Start at assumed open position

        # Current base velocity
        self.linear_x = 0.0
        self.angular_z = 0.0

        self.lock = threading.Lock()

        # Publish base velocity at 20 Hz
        self.timer = self.create_timer(
            0.05,
            self.publish_velocity
        )

        self.get_logger().info('Robot Teleop initialized')

    def publish_velocity(self):
        msg = TwistStamped()

        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'base_footprint'

        msg.twist.linear.x = self.linear_x
        msg.twist.angular.z = self.angular_z

        self.cmd_vel_pub.publish(msg)

    def stop_base(self):
        self.linear_x = 0.0
        self.angular_z = 0.0
        self.publish_velocity()
        self.get_logger().info('Base stopped')

    def move(self, linear=0.0, angular=0.0):
        self.linear_x = linear
        self.angular_z = angular

        self.get_logger().info(
            f'Base: linear={linear:.2f} m/s, '
            f'angular={angular:.2f} rad/s'
        )

    def publish_position(self, publisher, position):
        msg = Float64MultiArray()
        msg.data = [float(position)]
        publisher.publish(msg)

    def lift_up(self):
        self.lift_position = min(
            self.lift_position + self.lift_step,
            self.lift_max
        )
        self.publish_position(self.lift_pub, self.lift_position)

        self.get_logger().info(
            f'Lift position: {self.lift_position:.3f} m'
        )

    def lift_down(self):
        self.lift_position = max(
            self.lift_position - self.lift_step,
            self.lift_min
        )
        self.publish_position(self.lift_pub, self.lift_position)

        self.get_logger().info(
            f'Lift position: {self.lift_position:.3f} m'
        )

    def gripper_open(self):
        self.gripper_position = min(
            self.gripper_position + self.gripper_step,
            self.gripper_max
        )
        self.publish_position(
            self.gripper_pub,
            self.gripper_position
        )

        self.get_logger().info(
            f'Gripper position: {self.gripper_position:.3f}'
        )

    def gripper_close(self):
        self.gripper_position = max(
            self.gripper_position - self.gripper_step,
            self.gripper_min
        )
        self.publish_position(
            self.gripper_pub,
            self.gripper_position
        )

        self.get_logger().info(
            f'Gripper position: {self.gripper_position:.3f}'
        )

    def handle_key(self, key):
        key = key.lower()

        # Base movement
        if key == 'w':
            self.move(linear=self.linear_speed)
        elif key == 's':
            self.move(linear=-self.linear_speed)
        elif key == 'a':
            self.move(angular=self.angular_speed)
        elif key == 'd':
            self.move(angular=-self.angular_speed)
        elif key == ' ':
            self.stop_base()

        # Lift
        elif key == 'i':
            self.lift_up()
        elif key == 'k':
            self.lift_down()

        # Gripper
        elif key == 'j':
            self.gripper_open()
        elif key == 'l':
            self.gripper_close()

        # Independent speed adjustment
        elif key == 'q':
            self.linear_speed = min(
                self.linear_speed + self.linear_speed_step,
                self.max_linear_speed
            )
            self.get_logger().info(
                f'Linear speed: {self.linear_speed:.2f} m/s'
            )

        elif key == 'z':
            self.linear_speed = max(
                0.0,
                self.linear_speed - self.linear_speed_step
            )
            self.get_logger().info(
                f'Linear speed: {self.linear_speed:.2f} m/s'
            )

        elif key == 'e':
            self.angular_speed = min(
                self.angular_speed + self.angular_speed_step,
                self.max_angular_speed
            )
            self.get_logger().info(
                f'Angular speed: {self.angular_speed:.2f} rad/s'
            )

        elif key == 'c':
            self.angular_speed = max(
                0.0,
                self.angular_speed - self.angular_speed_step
            )
            self.get_logger().info(
                f'Angular speed: {self.angular_speed:.2f} rad/s'
            )


def main(args=None):
    if not sys.stdin.isatty():
        print('Error: Run this program directly in a terminal.')
        return

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    rclpy.init(args=args)
    node = RobotTeleop()

    executor_thread = threading.Thread(
        target=rclpy.spin,
        args=(node,),
        daemon=True
    )
    executor_thread.start()

    print(HELP)
    print("Nhan Ctrl+C, Ctrl+Z hoac ESC de thoat.")

    try:
        # Raw mode: terminal sends control keys as bytes to this program.
        # This prevents Ctrl+C from being consumed as SIGINT and Ctrl+Z
        # from being consumed as SIGTSTP.
        tty.setraw(fd)

        while rclpy.ok():
            ready, _, _ = select.select([fd], [], [], 0.1)
            if not ready:
                continue

            key = os.read(fd, 1)

            # Ctrl+C = 0x03, Ctrl+Z = 0x1a, ESC = 0x1b
            if key in (b'\x03', b'\x1a', b'\x1b'):
                print("\r\nDang dung robot va thoat...")
                break

            try:
                node.handle_key(key.decode('utf-8'))
            except UnicodeDecodeError:
                continue

    except KeyboardInterrupt:
        # Fallback if the terminal or launcher still delivers SIGINT.
        print("\r\nNhan Ctrl+C - dang thoat...")

    finally:
        # Publish zero velocity while ROS is still running.
        try:
            node.stop_base()
            import time
            time.sleep(0.15)
        except Exception as exc:
            print(f"Warning while stopping robot: {exc}")

        # Restore terminal before printing or returning to the shell.
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass

        if rclpy.ok():
            rclpy.shutdown()

        executor_thread.join(timeout=2.0)
        node.destroy_node()
        print("Da thoat chuong trinh.")


if __name__ == '__main__':
    main()

