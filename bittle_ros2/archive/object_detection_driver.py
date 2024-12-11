#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
import serial
import struct
import sys
import time
import math
from std_msgs.msg import String
from geometry_msgs.msg import Twist
from bittle_msgs.msg import Detection

dir_dict = {1: 'kcrF', -1: 'kbk', 2: 'kcrL', 3: 'kcrR', 0: 'kbalance', 4: 'kpone', 5: 'kptwo', 6: 'kpthree', 7: 'kpfour', 8: 'kcollectF', 9: 'kturn'}


class Driver(Node):

    def __init__(self, port='/dev/ttyAMA0'):
        super().__init__('cmd_vel_listener')
        self.dir = 0
        self.num_commands_sent = 0
        self.last_command_time = 0
        self.command_interval = 1
        self.subscription = self.create_subscription(
            Detection,
            '/detection_topic',
            self.callback,
            1)
        self.subscription  # prevent unused variable warning
        self.ser = serial.Serial(
            port=port,
            baudrate=115200,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=1
        )

        # make flags to keep track of the state of the mission
        self.mission_complete = False
        self.found_acorn = False
        self.collecting = False
        self.searching = True
        self.collected = False

        # keep track of how many pheromones have been dropped
        self.black_pheromones_dropped = 0
        self.white_pheromones_dropped = 0

    def callback(self, msg): # for processing the detection messages
        self.get_logger().info("Received a /detection_topic message!")

        results = list(msg.results) # returns a list with numeric labels for the objects 0: acorn 1: black pheromone 2: white pheromone
        xywhn_list = list(msg.xywhn_list) #returns a list with the x, y, width, height, of each detection, ordered by the from the top of the frame to the bottom
        # make lists to store detection info
        self.acorn_list = []
        self.black_pheromone_list = []
        self.white_pheromone_list = []
        for i in range(len(results)): # for each detection, append the xywhn_list to the appropriate list
            if results[i] == 0:
                self.acorn_list.append(xywhn_list[(i*4):(4*(i+1))])
            elif results[i] == 1:
                self.black_pheromone_list.append(xywhn_list[(i*4):(4*(i+1))])
            elif results[i] == 2:
                self.white_pheromone_list.append(xywhn_list[(i*4):(4*(i+1))])


        print("Acorn List: ", self.acorn_list)
        print("Black Pheromone List: ", self.black_pheromone_list)
        print("White Pheromone List: ", self.white_pheromone_list)

        self.command_logic()

    def command_logic(self):     
        current_time = time.time()
        time_since_last_command = current_time - self.last_command_time
        if len(self.acorn_list) > 0:
            if self.found_acorn == False:
                self.found_acorn = True
                self.searching = False
                self.collecting = True
                print("found acorn")
            if self.acorn_list[-1][0] > 0.75:
                print("turning right")
                dir = 3
            elif self.acorn_list[-1][0] < 0.25:
                print("turning left")
                dir = 2
            elif self.acorn_list[-1][1] > 0.85:
                print("collecting acorn")
                dir = 8
            else:
                print("going straight")
                dir = 1
        elif self.searching:
            if len(self.black_pheromone_list) > 0:
                print("found black pheromone")
                if self.black_pheromone_list[-1][0] > 0.75:
                    print("turning right")
                    dir = 3
                elif self.black_pheromone_list[-1][0] < 0.25:
                    print("turning left")
                    dir = 2
                else:
                    print("going straight")
                    dir = 1
            elif len(self.white_pheromone_list) > 0 and len(self.black_pheromone_list) == 0:
                print("found white pheromone")
                if self.white_pheromone_list[-1][0] > 0.75:
                    print("turning right")
                    dir = 3
                elif self.white_pheromone_list[-1][0] < 0.25:
                    print("turning left")
                    dir = 2
                else:
                    print("going straight")
                    dir = 1
            else:
                print("no detections")
                dir = 9
        else:
            dir = 0
        
        if time_since_last_command >= 5:  # drop pheromones every 5 seconds
            if self.found_acorn:
                if self.black_pheromones_dropped <= 9:
                    dir = 4
                else:
                    dir = 5
            elif self.searching:
                if self.white_pheromones_dropped <= 9:
                    dir = 6
                else:
                    dir = 7

        if self.dir != dir:
            self.wrapper([dir_dict[dir], 0])
            self.dir = dir
            self.num_commands_sent += 1
            self.last_command_time = current_time
    
    def drop_pheromone(self):
        if self.found_acorn:
            if self.black_pheromones_dropped <= 9:
                dir = 4
            else:
                dir = 5
        elif self.searching:
            if self.white_pheromones_dropped <= 9:
                dir = 6
            else:
                dir = 7



    def wrapper(self, task):  # Structure is [token, var=[], time]
        print(task)
        if len(task) == 2:
            self.serialWriteByte([task[0]])
        elif isinstance(task[1][0], int):
            self.serialWriteNumToByte(task[0], task[1])
        else:
            self.serialWriteByte(task[1])
        time.sleep(task[-1])

    def serialWriteNumToByte(self, token, var=[]):  # Only to be used for c m u b i l o within Python
        # print("Num Token "); print(token);print(" var ");print(var);print("\n\n");
        if token == 'l' or token == 'i':
            var = list(map(lambda x: int(x), var))
            instrStr = token + struct.pack('b' * len(var), *var) + '~'
        elif token == 'c' or token == 'm' or token == 'u' or token == 'b':
            instrStr = token + str(var[0]) + " " + str(var[1]) + '\n'
        print("!!!!" + instrStr)
        self.ser.write(instrStr.encode())

    def serialWriteByte(self, var=[]):
        token = var[0][0]
        if (token == 'c' or token == 'm' or token == 'b' or token == 'u') and len(var) >= 2:
            instrStr = ""
            for element in var:
                instrStr = instrStr + element + " "
        elif token == 'l' or token == 'i':
            if (len(var[0]) > 1):
                var.insert(1, var[0][1:])
            var[1:] = list(map(lambda x: int(x), var[1:]))
            instrStr = token + struct.pack('b' * len(var[1:]), *var[1:]) + '~'
        elif token == 'w' or token == 'k':
            instrStr = var[0] + '\n'
        else:
            instrStr = token
        print("!!!!!!! " + instrStr)
        self.ser.write(instrStr.encode())


def main(args=None):
    rclpy.init(args=args)
    driver = Driver()
    rclpy.spin(driver)

    # Destroy the node explicitly
    # (optional - otherwise it will be done automatically
    # when the garbage collector destroys the node object)
    driver.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

