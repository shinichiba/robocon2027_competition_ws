import json
import time
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

class CompetitionManager(Node):
    def __init__(self):
        super().__init__('competition_manager')
        self.declare_parameter('match_duration_sec', 180.0)
        self.declare_parameter('points_per_cube', 20)
        self.duration = float(self.get_parameter('match_duration_sec').value)
        self.points = int(self.get_parameter('points_per_cube').value)
        self.running = False
        self.started = None
        self.blocks = {'robot1': set(), 'robot2': set()}
        self.pub = self.create_publisher(String, '/competition/scoreboard', 10)
        self.create_subscription(String, '/competition/robot1/placed_block',
                                  lambda m: self.record('robot1', m.data), 10)
        self.create_subscription(String, '/competition/robot2/placed_block',
                                  lambda m: self.record('robot2', m.data), 10)
        self.create_service(Trigger, '/competition/start', self.start)
        self.create_service(Trigger, '/competition/stop', self.stop)
        self.timer = self.create_timer(0.2, self.tick)
        self.get_logger().info('Ready. Call /competition/start.')

    def start(self, req, res):
        self.blocks = {'robot1': set(), 'robot2': set()}
        self.started = time.monotonic()
        self.running = True
        res.success, res.message = True, 'Match started; scores reset.'
        return res

    def stop(self, req, res):
        self.running = False
        res.success, res.message = True, 'Match stopped.'
        return res

    def record(self, robot, block_id):
        if not self.running or not block_id.strip():
            return
        self.blocks[robot].add(block_id.strip())

    def tick(self):
        elapsed = 0.0 if self.started is None else time.monotonic() - self.started
        if self.running and elapsed >= self.duration:
            self.running = False
        data = {
            'running': self.running,
            'elapsed_sec': round(elapsed, 1),
            'remaining_sec': max(0.0, round(self.duration - elapsed, 1)),
            'robot1': {'blocks': sorted(self.blocks['robot1']),
                       'score': len(self.blocks['robot1']) * self.points},
            'robot2': {'blocks': sorted(self.blocks['robot2']),
                       'score': len(self.blocks['robot2']) * self.points},
            'verification': 'strategy-reported; not independently checked in Gazebo'
        }
        msg = String()
        msg.data = json.dumps(data)
        self.pub.publish(msg)

def main():
    rclpy.init()
    node = CompetitionManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
