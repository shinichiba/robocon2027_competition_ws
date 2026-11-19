# Example strategy logic (copy into the student's own ROS 2 package).
# Navigation action: /robot1/navigate_to_pose
# Lift command: /robot1/lift_position_controller/commands (Float64MultiArray)
# Gripper command: /robot1/gripper_position_controller/commands (Float64MultiArray)
# Score report: /competition/robot1/placed_block (std_msgs/String)
#
# The student must implement visual/known-coordinate cube localization, approach
# pose generation, grasp verification, lift verification, stack alignment and
# stable-placement verification. A command sent is not a successful grasp.
