
#!/usr/bin/env python3
import sys
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

  + / - : Tăng / giảm tốc độ di chuyển
  Q     : Thoát chương trình

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
            '/diff_drive_controller/cmd_vel',
            10
        )

        self.lift_pub = self.create_publisher(
            Float64MultiArray,
            '/lift_controller/commands',
            10
        )

        self.gripper_pub = self.create_publisher(
            Float64MultiArray,
            '/gripper_controller/commands',
            10
        )

        # Linear/angular velocity
        self.linear_speed = 2.50       # m/s
        self.angular_speed = 3.00      # rad/s
        self.speed_step = 0.1

        # Lift joint limits (edit to match your URDF)
        self.lift_min = -0.50          # m
        self.lift_max = 0.50           # m
        self.lift_step = 0.02          # m
        self.lift_position = 0.00

        # Gripper limits (edit to match your URDF)
        self.gripper_min = 0.00        # m or rad
        self.gripper_max = 0.35        # m or rad
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

        # Speed adjustment
        elif key == '+':
            self.linear_speed += self.speed_step
            self.angular_speed += self.speed_step
            self.get_logger().info(
                f'Speeds: linear={self.linear_speed:.2f}, '
                f'angular={self.angular_speed:.2f}'
            )
        elif key == '-':
            self.linear_speed = max(
                0.0, self.linear_speed - self.speed_step
            )
            self.angular_speed = max(
                0.0, self.angular_speed - self.speed_step
            )
            self.get_logger().info(
                f'Speeds: linear={self.linear_speed:.2f}, '
                f'angular={self.angular_speed:.2f}'
            )


def main(args=None):
    if not sys.stdin.isatty():
        print('Error: Run this program in a terminal.')
        return

    rclpy.init(args=args)
    node = RobotTeleop()

    old_settings = termios.tcgetattr(sys.stdin)
    executor_thread = threading.Thread(
        target=rclpy.spin,
        args=(node,),
        daemon=True
    )
    executor_thread.start()

    print(HELP)

    try:
        tty.setcbreak(sys.stdin.fileno())

        while rclpy.ok():
            ready, _, _ = select.select([sys.stdin], [], [], 0.1)

            if not ready:
                continue

            key = sys.stdin.read(1)

            if key.lower() == 'q':
                break

            node.handle_key(key)

    except KeyboardInterrupt:
        pass

    finally:
        # Stop the base before exiting
        node.stop_base()

        # Restore terminal settings
        termios.tcsetattr(
            sys.stdin,
            termios.TCSADRAIN,
            old_settings
        )

        node.destroy_node()
        rclpy.shutdown()
        executor_thread.join(timeout=1.0)


if __name__ == '__main__':
    main()

