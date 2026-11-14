#!/usr/bin/env python3

"""
Visualization-only aggregator for two independent ROS 2 TF trees.

Input topics:
  /robot1/tf
  /robot2/tf
  /robot1/tf_static
  /robot2/tf_static

Output topics:
  /tf_viz
  /tf_static_viz

The node never publishes to /tf or /tf_static. Nav2 and SLAM keep
using their original per-robot TF topics.

It also adds visualization-only anchors:
  viz_world -> robot1/map
  viz_world -> robot2/map

These anchors let RViz use one Fixed Frame and display both robots.
The configured map origins are assumed to coincide with the robots'
initial Gazebo spawn poses. Change the launch parameters if the
initial poses change or if your map origins are initialized differently.
"""

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSProfile,
    ReliabilityPolicy,
    DurabilityPolicy,
    HistoryPolicy,
)
from geometry_msgs.msg import TransformStamped
from tf2_msgs.msg import TFMessage


class TfAggregator(Node):
    def __init__(self):
        super().__init__('tf_aggregator')

        dynamic_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=100,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )

        static_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=100,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )

        self.dynamic_pub = self.create_publisher(
            TFMessage, '/tf_viz', dynamic_qos
        )
        self.static_pub = self.create_publisher(
            TFMessage, '/tf_static_viz', static_qos
        )

        self.tf_static_transforms = {}
        self.odom_subscriptions = []

        for robot_ns in ('robot1', 'robot2'):
            self.odom_subscriptions.append(
                self.create_subscription(
                    TFMessage,
                    f'/{robot_ns}/tf',
                    self.dynamic_callback,
                    dynamic_qos
                )
            )
            self.odom_subscriptions.append(
                self.create_subscription(
                    TFMessage,
                    f'/{robot_ns}/tf_static',
                    self.static_callback,
                    static_qos
                )
            )

        # Connect the two otherwise-independent map roots only in the
        # visualization copy. Nav2 never subscribes to these transforms.
        self.visualization_anchors = [
            self.make_anchor(
                'robot1/map',
                self.get_parameter_value('robot1_map_x', -4.7),
                self.get_parameter_value('robot1_map_y', -4.7),
                self.get_parameter_value('robot1_map_yaw', 0.785398)
            ),
            self.make_anchor(
                'robot2/map',
                self.get_parameter_value('robot2_map_x', 4.7),
                self.get_parameter_value('robot2_map_y', 4.7),
                self.get_parameter_value('robot2_map_yaw', -2.35619)
            ),
        ]

        self.publish_static_snapshot()

        self.get_logger().info(
            'TF visualization aggregator ready. '
            'Inputs: /robot1/tf, /robot2/tf, '
            '/robot1/tf_static, /robot2/tf_static. '
            'Outputs: /tf_viz, /tf_static_viz. '
            'RViz Fixed Frame: viz_world.'
        )

    def get_parameter_value(self, name, default):
        self.declare_parameter(name, default)
        return float(self.get_parameter(name).value)

    def make_anchor(self, child_frame, x, y, yaw):
        t = TransformStamped()
        t.header.frame_id = 'viz_world'
        t.child_frame_id = child_frame
        t.transform.translation.x = x
        t.transform.translation.y = y
        t.transform.translation.z = 0.0

        # Planar yaw quaternion.
        t.transform.rotation.x = 0.0
        t.transform.rotation.y = 0.0
        t.transform.rotation.z = math.sin(yaw / 2.0)
        t.transform.rotation.w = math.cos(yaw / 2.0)
        return t

    def dynamic_callback(self, msg: TFMessage):
        if msg.transforms:
            self.dynamic_pub.publish(msg)

    def static_callback(self, msg: TFMessage):
        changed = False

        for transform in msg.transforms:
            child = transform.child_frame_id
            if not child:
                continue
            self.tf_static_transforms[child] = transform
            changed = True

        if changed:
            self.publish_static_snapshot()

    def publish_static_snapshot(self):
        combined = TFMessage()
        combined.transforms = (
            list(self.tf_static_transforms.values())
            + self.visualization_anchors
        )
        self.static_pub.publish(combined)


def main(args=None):
    rclpy.init(args=args)
    node = TfAggregator()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
