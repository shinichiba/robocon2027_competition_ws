
#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSProfile,
    ReliabilityPolicy,
    DurabilityPolicy,
    HistoryPolicy
)

from nav_msgs.msg import Odometry
from tf2_msgs.msg import TFMessage
from geometry_msgs.msg import TransformStamped


class OdomTfSplitter(Node):

    def __init__(self):
        super().__init__('odom_tf_splitter')

        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=50,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE
        )

        # Dictionary chứa publisher TF riêng của từng robot
        self.tf_publishers = {}

        self.odom_subscriptions = []

        for robot in ['robot1', 'robot2']:

            self.tf_publishers[robot] = self.create_publisher(
                TFMessage,
                f'/{robot}/tf',
                qos
            )

            sub = self.create_subscription(
                Odometry,
                f'/{robot}/diff_drive_controller/odom',
                lambda msg, ns=robot: self.odom_callback(msg, ns),
                qos
            )

            self.odom_subscriptions.append(sub)

            self.get_logger().info(
                f'Subscribed: /{robot}/diff_drive_controller/odom'
            )

            self.get_logger().info(
                f'Publishing: /{robot}/tf'
            )

    def odom_callback(self, msg, robot):

        transform = TransformStamped()

        transform.header.stamp = msg.header.stamp
        transform.header.frame_id = msg.header.frame_id
        transform.child_frame_id = msg.child_frame_id

        transform.transform.translation.x = (
            msg.pose.pose.position.x
        )

        transform.transform.translation.y = (
            msg.pose.pose.position.y
        )

        transform.transform.translation.z = (
            msg.pose.pose.position.z
        )

        transform.transform.rotation = (
            msg.pose.pose.orientation
        )

        tf_msg = TFMessage()
        tf_msg.transforms.append(transform)

        self.tf_publishers[robot].publish(tf_msg)


def main(args=None):

    rclpy.init(args=args)

    node = OdomTfSplitter()

    try:
        rclpy.spin(node)

    except KeyboardInterrupt:
        pass

    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

