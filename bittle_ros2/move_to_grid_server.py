import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer
from bittle_msgs.action import MoveToGrid
from bittle_msgs.msg import Detection, Command
from rclpy.callback_groups import ReentrantCallbackGroup
import numpy as np


class MoveToGridServer(Node):
    def __init__(self):
        super().__init__('move_to_grid_server')
        self.callback_group = ReentrantCallbackGroup()
        self._action_server = ActionServer(
            self,
            MoveToGrid,
            'move_to_grid',
            self.execute_callback,
            callback_group=self.callback_group
        )
        self.detection_subscription = self.create_subscription(
            Detection,
            'detection',
            self.detection_callback,
            10,
            callback_group=self.callback_group
        )
        self.command_publisher = self.create_publisher(
            Command,
            'command',
              10,
              callback_group=self.callback_group
        )
        self.get_logger().info('MoveToGridServer has been started.')

        self.target_square = None
        self.current_heading = None
        self.current_position = None
        self.error = None
        self.detections = []
        self.current_cmd = 'Krest'
        self.crawl_threshold = 10
        self.turn_threshold = 40

        self.grid_centers = {
            "A1": (80, 60), "A2": (240, 60), "A3": (400, 60), "A4": (560, 60),
            "B1": (80, 180), "B2": (240, 180), "B3": (400, 180), "B4": (560, 180),
            "C1": (80, 300), "C2": (240, 300), "C3": (400, 300), "C4": (560, 300),
            "D1": (80, 420), "D2": (240, 420), "D3": (400, 420), "D4": (560, 420)
        }

    def execute_callback(self, goal_handle):
        self.get_logger().info('Executing goal...')
        feedback_msg = self.current_position
        self.target_square = goal_handle.request.target_square
        self.get_logger().info(f'Target square: {self.target_square}')
        if self.target_square is not None:
            if self.error is None or self.error > 20:
                self.navigate_to_target()
            else:
                goal_handle.succeed()
        result = feedback_msg
        return result

    def navigate_to_target(self):
        if self.current_heading is None:
            self.get_logger().info('Current heading not available.')
            return

        if not self.detections:
            self.get_logger().info('No detections available.')
            return

        # Get the position of the robot
        robot_position = self.current_position

        if not robot_position:
            self.get_logger().info('Robot not detected.')
            return

        self.previous_robot_position = robot_position

        target_position = self.grid_centers[self.target_square]
        direction_vector = (target_position[0] - robot_position[0], robot_position[1] - target_position[1])
        self.get_logger().info(f'Direction vector: {direction_vector}')
        self.move_towards_target(direction_vector)

    def move_towards_target(self, direction_vector):
        dx, dy = direction_vector
        self.get_logger().info(f'dx: {dx}, dy: {dy}')
        error = np.sqrt(dx**2 + dy**2)
        self.error = error
        self.get_logger().info(f'Error: {error}')
        Txhat = dx / error
        Tyhat = dy / error
        Rxhat = np.cos(self.current_heading * np.pi / 180)
        Ryhat = np.sin(self.current_heading * np.pi / 180)
        TdotR = Txhat * Rxhat + Tyhat * Ryhat
        magnitude_T = np.sqrt(Txhat**2 + Tyhat**2)
        magnitude_R = np.sqrt(Rxhat**2 + Ryhat**2)
        self.get_logger().info(f'TdotR: {TdotR}, magnitude_T: {magnitude_T}, magnitude_R: {magnitude_R}')
        self.get_logger().info(f'Txhat: {Txhat}, Tyhat: {Tyhat}, Rxhat: {Rxhat}, Ryhat: {Ryhat}')
        theta = np.arccos(Txhat * Rxhat + Tyhat * Ryhat) * 180 / np.pi
        self.get_logger().info(f'Theta: {theta}')
        self.get_logger().info(f'Current heading: {self.current_heading}')
        if error > 20:
            self.adjust_heading(theta)
        else:
            self.get_logger().info('Reached target square.')
            self.publish_command('krest',0.0)
            return


    def adjust_heading(self, theta):
        if abs(theta) < self.crawl_threshold:
            self.publish_command('kcrF',0.0)
        elif abs(theta) > self.turn_threshold:
            if theta > 0:
                self.publish_command('kvtL',0.5)
            else:
                self.publish_command('kvtR',0.5)
        elif self.turn_threshold > abs(theta) > self.crawl_threshold:
            if theta > 0:
                self.publish_command('kcrL',0.5)
            else:
                self.publish_command('kcrR',0.5)

    def publish_command(self, command, delay):
        if command != self.current_cmd:
            self.current_cmd = command
            msg = Command()
            msg.cmd = [command]
            msg.delay = [delay]
            self.command_publisher.publish(msg)
            self.get_logger().info(f'Publishing: {msg.cmd} with delay {msg.delay}')
        else:
            self.get_logger().info(f'Command already published: {command}')

    def detection_callback(self, msg):
        self.current_heading = msg.april_tag_orientation
        self.current_position = msg.april_tag_location
        centers = list(zip(*(iter(msg.center),) * 2))

        for class_name, grid_square, center in zip(msg.class_names, msg.grid_squares, centers):
            center_x, center_y = center[0], center[1]
            self.detections.append((class_name, grid_square, (center_x, center_y)))
        
        self.get_logger().info(f'class names: {msg.class_names}, grid squares: {msg.grid_squares}, Centers: {centers}')
        self.get_logger().info(f'Received detections: {self.detections}')




def main(args=None):
    rclpy.init(args=args)
    move_to_grid_server = MoveToGridServer()
    rclpy.spin(move_to_grid_server)
    rclpy.shutdown()

if __name__ == '__main__':
    main()