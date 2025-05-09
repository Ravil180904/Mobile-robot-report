import rclpy 
from rclpy.node import Node
from rclpy.action import ActionClient
from ugv_interface.action import Behavior
from sensor_msgs.msg import Image
from rcl_interfaces.msg import ParameterDescriptor
from cv_bridge import CvBridge
from gpiozero import OutputDevice
from time import sleep
import cv2
import numpy as np
import json
import threading

class ColorTracker(Node):
    def __init__(self):
        super().__init__('color_tracker')

        self.image_raw_subscription = self.create_subscription(Image, '/image_raw', self.image_callback, 10)
        self._action_client = ActionClient(self, Behavior, 'behavior')
        self.color_track_publisher = self.create_publisher(Image, '/color_track/result', 10)
        self.bridge = CvBridge()
        self.relay = OutputDevice(18, active_high=True, initial_value=False)
        self.firing = False  # Prevent multiple simultaneous firing threads

        # Declare HSV parameters
        self.declare_parameter("lower_hue", 0, ParameterDescriptor(description="Lower Hue"))
        self.declare_parameter("lower_saturation", 115, ParameterDescriptor(description="Lower Saturation"))
        self.declare_parameter("lower_value", 0, ParameterDescriptor(description="Lower Value"))
        self.declare_parameter("upper_hue", 5, ParameterDescriptor(description="Upper Hue"))
        self.declare_parameter("upper_saturation", 255, ParameterDescriptor(description="Upper Saturation"))
        self.declare_parameter("upper_value", 255, ParameterDescriptor(description="Upper Value"))

    def fire(self):
        if self.firing:
            return
        self.firing = True
        def shoot():
            for _ in range(4):  # 4 shots in 20 seconds total (every 5 seconds)
                self.relay.on()
                sleep(1)
                self.relay.off()
                sleep(4)
            self.firing = False
        threading.Thread(target=shoot).start()

    def send_goal(self, command):
        if not self._action_client.wait_for_server(timeout_sec=0.0):
            self.get_logger().error('Action server not available!')
            return

        goal_msg = Behavior.Goal()
        goal_msg.command = command
        self._send_goal_future = self._action_client.send_goal_async(goal_msg)
        self._send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('Goal rejected :(')
            return

        self.get_logger().info('Goal accepted')
        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        result = future.result().result
        self.get_logger().info(f'Result: {result.result}')

    def image_callback(self, msg):
        frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        lower_color = np.array([
            self.get_parameter("lower_hue").value,
            self.get_parameter("lower_saturation").value,
            self.get_parameter("lower_value").value
        ])
        upper_color = np.array([
            self.get_parameter("upper_hue").value,
            self.get_parameter("upper_saturation").value,
            self.get_parameter("upper_value").value
        ])

        mask = cv2.inRange(hsv, lower_color, upper_color)
        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if 30 < w < 300 and 10 < h < 300:
                cx = x + w // 2
                cy = y + h // 2
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.circle(frame, (cx, cy), 5, (255, 0, 0), -1)
                self.get_logger().info(f'Tracking block at ({cx}, {cy})')

                if abs(cx - 320) < 30 and abs(cy - 240) < 30:
                    print("Fire: Object in center")
                    self.fire()
                else:
                    print("Object detected but not in center - no fire")

                # Movement control
                if (cx - 320) > 30:
                    print("turn right")
                    data = [{"T": 1, "type": "spin", "data": -1}]
                elif (320 - cx) > 30:
                    print("turn left")
                    data = [{"T": 1, "type": "spin", "data": 1}]
                elif (240 - cy) > 30:
                    print("move forward")
                    data = [{"T": 1, "type": "drive_on_heading", "data": 0.01}]
                elif (cy - 240) > 30:
                    print("move back")
                    data = [{"T": 1, "type": "back_up", "data": 0.01}]
                else:
                    print("stop")
                    data = [{"T": 1, "type": "stop", "data": 0}]

                json_str = json.dumps(data)
                self.send_goal(json_str)

        result_img_msg = self.bridge.cv2_to_imgmsg(frame, encoding="bgr8")
        self.color_track_publisher.publish(result_img_msg)
        cv2.imshow('Tracked Image', frame)
        cv2.waitKey(1)

def main(args=None):
    rclpy.init(args=args)
    color_tracker = ColorTracker()
    rclpy.spin(color_tracker)
    color_tracker.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
