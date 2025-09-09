#!/usr/bin/python

##version1    210222
##version1_2  210330
#version3(seokju) 231102

# library import
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5 import *
import sys
import os
import requests
import subprocess
import time
import sensor
import multiplexer
from RS485Event import RS485Event
from rpi_backlight import Backlight
import threading
import logging
import logging.handlers
import socket
from Config import Config
from recall_system import RECALL
from smtp import SMTP
import RPi.GPIO as GPIO
from functools import wraps
import signal
import errno

sys.path.append('/home/pi')

GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)

smtp = SMTP()

# make log files
current_dir = os.path.dirname(os.path.realpath(__file__))
log_dir = '{}/logs'.format(current_dir)
if not os.path.exists(log_dir):
    os.makedirs(log_dir)
try :
    logger = logging.getLogger("crumbs")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s > %(message)s')
    fileHandler = logging.handlers.TimedRotatingFileHandler(filename='./logs/datalog',
                                                            when='midnight', encoding='utf-8')
    fileHandler.suffix = '%y%m%d'
    fileHandler.setFormatter(formatter)
    logger.addHandler(fileHandler)
except Exception as e:
    f = open("./log/logerror.txt",'w')
    f.write(e)
    f.close()

def initGPIO():
    try:
        global green_pin, yellow_pin, red_pin, buzzer_pin, out1_pin, out2_pin, out3_pin, out4_pin
        config = Config('config_th.ini', debug=False)
        green_pin = config.getValue('Setting', 'green')
        yellow_pin = config.getValue('Setting', 'yellow')
        red_pin = config.getValue('Setting', 'red')
        buzzer_pin = config.getValue('Setting', 'buzzer')
        out1_pin = config.getValue('Setting', 'out1')
        out2_pin = config.getValue('Setting', 'out2')
        out3_pin = config.getValue('Setting', 'out3')
        out4_pin = config.getValue('Setting', 'out4')
        GPIO.setup(green_pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(yellow_pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(red_pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(buzzer_pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(out1_pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(out2_pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(out3_pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(out4_pin, GPIO.OUT, initial=GPIO.LOW)
        #SETDATE = "sudo /usr/bin/rdate -s 10.141.13.88"
        #os.system(SETDATE)
    except Exception as e:
        logger.debug(f"[{sys._getframe().f_code.co_name}][Exception] : {e}")
initGPIO()

def controlGPIO(pin, status):
    try:
        GPIO.output(pin, status)
    except Exception as e:
        logger.debug(f"[{sys._getframe().f_code.co_name}][Exception] : {e}")

class Main(QWidget):
    print("Program Start")
    logger.debug("Program Start")
    webservice_flag = 0 # 0 : webservice mode Off / 1 : webservice mode On
    delay_flag = 0 # 0 : no delaytimer / 1 : during delay timer / 2 : finish delay timer
    delay_flag_Ndelay = 0
    setconfig_flag = 0
    current_timer = None # delay timer
    web_status = 0
    wifi_status = 0
    hw_status = 0
    login_flag = 0
    loginIdx = 0
    settingIdx = 2
    tab_index_flag = 0
    
    #[240620_SeokJu.Yang_Add idLabelBackColor(if (QA_Alarm == 1) color changed red)
    idLabelBackColor = "#325d79"
    idLabelColor = "white"
    #]240620_SeokJu.Yang_Add idLabelBackColor(if (QA_Alarm == 1) color changed red)

    style_sheet = """
    QTabBar::tab {
        background: lightgray;
        color: black;
        border: 0;
        width: 90px;
        height: 18px;
        padding: 1px;
        padding-left:7px;
        margin-right: 6px;
    }
    QTabWidget::tab{background-color:black;}
    QTabBar::tab:selected {background-color:#f1e6c1;font-size:10pt;}
    QTabBar::tab:!selected {background-color:lightgray;;font-size:10pt;}
    """

    def __init__(self):
        super().__init__()
        print("validation start")
        self.start_program_qa_validation()
        print("validation finished")
        self.initUI()
        self.initSignal()
        self.checkWifiConnected()
        self.tabWidget.setCurrentIndex(1)
        self.tab_monitor.getDataFromSensor()
        
        self.timer_wifi = QTimer(self)
        self.timer_wifi.setInterval(5000)
        self.timer_wifi.timeout.connect(self.checkWifiConnected)
        self.timer_wifi.start()
        
        #[250909_SeokJu.Yang_add alive check timer
        self.aliveCheckTimer = QTimer(self)
        self.aliveCheckTimer.setInterval(3000)
        self.aliveCheckTimer.timeout.connect(self.AliveCheck)
        self.aliveCheckTimer.start()
        #]250909_SeokJu.Yang_add alive check timer
        
    #[250909_SeokJu.Yang_add alive check timer
    def AliveCheck(self):
        try:
            if not self.timer_wifi.isActive():
                logger.debug("self.timer_wifi restart")
                self.timer_wifi.start()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    #[250909_SeokJu.Yang_add alive check timer
    
    
    # def onChange(self, i):  # change tab restart timer
    #     if i == 2:
    #         self.tab_index_flag = 1
    #     if i == 1 & self.tab_index_flag == 1:
    #         self.config = Config('config_th.ini', debug=False)
    #         self.tab_monitor.timer_read.start()
    #         self.tab_monitor.timer_write.start()
    #         self.tab_index_flag == 0
    
    def start_program_qa_validation(self):
        try:
            self.config = Config('config_th.ini', debug=False)
            self.serial_number = self.config.getValue('Setting', 'serial_number')
            self.id = self.config.getValue('Setting', 'id')
            self.kit_db = RECALL()
            self.kit_data = self.kit_db.Set_Config(self.serial_number) # [(datetime.date(2023, 8, 22), 'SSTN0005F', 'K5')]

            # not registered
            if self.kit_data == []:
                self.config.setValue("Setting", "QA_Alarm", 1)
                self.config.save()
                
                # [add] find IP Address + Send E-mail to Plant
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    sock.connect(("pwnbit.kr",443))
                    sock.settimeout(None)
                    not_registered_title = "WIP thermo-hygrometer : Use not registered equipment\n"

                    if sock.getsockname()[0][4] == '2':
                        not_registered_plant = 0
                        not_registered_text = f" [K3]Use not registered Equipment\n IP : {sock.getsockname()[0]}\n Setting id : {self.id}\n Serial Number : {self.serial_number}"
                        smtp.Send_Mail(not_registered_plant, not_registered_title, not_registered_text)
                        logger.debug("[Success]Not registered Equipment - QA send mail")
                    elif sock.getsockname()[0][4] == '3':
                        not_registered_plant = 1
                        not_registered_text = f" [K4]Use not registered Equipment\n IP : {sock.getsockname()[0]}\n Setting id : {self.id}\n Serial Number : {self.serial_number}"
                        smtp.Send_Mail(not_registered_plant, not_registered_title, not_registered_text)
                        logger.debug("[Success]Not registered Equipment - QA send mail")
                    elif sock.getsockname()[0][4] == '4':
                        not_registered_plant = 2
                        not_registered_text = f" [K5]Use not registered Equipment\n IP : {sock.getsockname()[0]}\n Setting id : {self.id}\n Serial Number : {self.serial_number}"
                        smtp.Send_Mail(not_registered_plant, not_registered_title, not_registered_text)
                        logger.debug("[Success]Not registered Equipment - QA send mail")
                    else:
                        logger.debug("[Fail]Not registered Equipment - QA send mail")
                        print("Wrong Plant IP")
                except Exception as e:
                    logger.debug(f"[Fail]Not registered Equipment - QA send mail : {e}")
            # DB Connect Fail
            elif self.kit_data == "DB Connect Fail":
                logger.debug("[Fail] Start Program DB Connect Fail")
            # registered
            else:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    sock.connect(("pwnbit.kr",443))
                    sock.settimeout(None)
                    self.current_plant = int(self.kit_data[0][2][1])
                    check_status = self.kit_data[0][3].upper()
                    if check_status == 'YES':
                        self.config.setValue("Setting", "QA_Alarm", 0)
                        self.config.save()
                        print("Allowed Equipment")
                    else:
                        self.config.setValue("Setting", "QA_Alarm", 1)
                        self.config.save()
                        logger.debug(f"QA Alarm Changed : {check_status}")
                        
                        status_no_title = "WIP thermo-hygrometer : Use status 'NO' equipment"
                        status_no_text = f" [K{self.current_plant}]Use status 'NO' Equipment\n IP : {sock.getsockname()[0]}\n Location : {self.kit_data[0][4]}\n Setting id : {self.id}\n Serial_Number : {self.serial_number}"
                        smtp.Send_Mail(int(self.current_plant)-2, status_no_title, status_no_text)
                        logger.debug("[Success]Use status 'No' Equipment - QA send mail")
                except Exception as e:
                    logger.debug("[Fail]Use status 'No' Equipment - QA send mail")
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

    def initUI(self):
        try:
            # self.config = Config('config_th.ini', debug=False)
            # self.version = self.config.getValue("Setting","version")
            self.setWindowTitle(f'Monitoring System_ATK_250909')
            self.setWindowFlags(Qt.Window)
            self.setGeometry(0, 0, 800, 450)

            palette = self.palette()
            color = QColor('#325d79')
            palette.setColor(self.backgroundRole(), color)
            self.setPalette(palette)

            self.id_label = QPushButton("ID: ")
            #[240620_SeokJu.Yang_Add idLabelBackColor(if (QA_Alarm == 1) color changed red)
            self.id_label.setStyleSheet(f"font : 8pt bold; color : white; background-color: {Main.idLabelBackColor}; border : none;")
            #]240620_SeokJu.Yang_Add idLabelBackColor(if (QA_Alarm == 1) color changed red)
            
            Main.set_id = self.config.getValue('Setting', 'id')

            self.id_label.setText('ID : {}'.format(Main.set_id))

            self.time_label = QLabel("")
            self.time_label.setStyleSheet("font : 8pt bold; color : #efeeee;")

            self.wifi_icon = QPushButton(" WIFI")
            self.wifi_icon.setStyleSheet("""
            qproperty-icon: url("./icon_th/wifi.png"); /* empty image */
            qproperty-iconSize: 13px 13px; /* space for the background image */
            color : white;
            font-size: 9px;
            """)
            self.wifi_icon.setMaximumSize(120, 10)
            self.wifi_icon.setFlat(True)

            self.hw_icon = QPushButton(" H/W")
            self.hw_icon.setStyleSheet("""
            qproperty-icon: url("./icon_th/laptop.png"); /* empty image */
            qproperty-iconSize: 13px 13px; /* space for the background image */
            color : white;
            font-size: 9px;
            background-color:#CDDC39;
            """)
            self.hw_icon.setMaximumSize(120, 10)
            self.hw_icon.setFlat(True)
            
            self.web_icon = QPushButton(" WEB")
            self.web_icon.setStyleSheet("""
            qproperty-icon: url("./icon_th/network.png"); /* empty image */
            qproperty-iconSize: 13px 13px; /* space for the background image */
            color : white;
            font-size: 9px;
            background-color:red;
            """)
            self.web_icon.setMaximumSize(120, 10)
            self.web_icon.setFlat(True)

            self.delay_button = QPushButton(" Delay")
            self.delay_button.setFlat(True)
            self.delay_button.setStyleSheet("""
            color : white;
            qproperty-icon: url("./icon_th/delaytime.png");
            qproperty-iconSize: 30px 30px; 
            QPushButton{background-color:#f26627; border-radius:1px; padding:2px; border-style:outset; color:white; border-radius:15px;}
            QPushButton:focus{border:none; outline:none;}
            QPushButton:hover{background-color:#f26627;}
            QPushButton:pressed{background-color:#f26627;}
            """)
            ###################################################

            self.max_button = QPushButton(" Full")
            self.max_button.setFlat(True)
            self.max_button.setStyleSheet("""
            color : white;
            qproperty-icon: url("./icon_th/expand.png");
            qproperty-iconSize: 30px 30px; 
            QPushButton{background-color:#f26627; border-radius:1px; padding:2px; border-style:outset; color:white; border-radius:15px;}
            QPushButton:focus{border:none; outline:none;}
            QPushButton:hover{background-color:#f26627;}
            QPushButton:pressed{background-color:#f26627;}
            """)

            self.close_button = QPushButton(" Exit")
            self.close_button.setFlat(True)
            self.close_button.setStyleSheet("""
            color : white;
            qproperty-icon: url("./icon_th/exit.png");
            qproperty-iconSize: 30px 30px; 
            QPushButton{background-color:#f26627; border-radius:1px; padding:2px; border-style:outset; color:white; border-radius:15px;}
            QPushButton:hover{background-color:#f26627;}
            QPushButton:pressed{background-color:#f26627;}
            """)

            self.wifi_label = QLabel(" Not Connected")
            self.wifi_label.setStyleSheet("color : red;")
            self.hw_label = QLabel(" Not Connected")
            self.hw_label.setStyleSheet("color : red;")
            self.web_label = QLabel(" Not Connected")
            self.web_label.setStyleSheet("color : red;")

            self.tabWidget = QTabWidget()
            # self.tabWidget.currentChanged.connect(self.onChange)

            p = self.tabWidget.palette()
            p.setColor(self.tabWidget.backgroundRole(), QtGui.QColor(52, 78, 92))
            self.tabWidget.setPalette(p)
            self.tab_login = Login()
            self.tab_monitor = Monitor()
            self.tab_popmonitor = PopMonitor()
            self.tab_setting = Setting()
            self.tabWidget.addTab(self.tab_login, "Login")
            self.tabWidget.addTab(self.tab_monitor, "Monitor")
            self.tabWidget.addTab(self.tab_setting, "Setting")
            self.tabWidget.tabBar().setCursor(QtCore.Qt.PointingHandCursor)

            self.tabWidget.setTabIcon(0, QtGui.QIcon('./icon_th/tab/0.png'))
            self.tabWidget.setTabIcon(1, QtGui.QIcon('./icon_th/tab/1_gray.png'))
            self.tabWidget.setTabIcon(2, QtGui.QIcon('./icon_th/tab/2_gray.png'))
            self.tabWidget.setIconSize(QtCore.QSize(16, 16))

            layout_title = QVBoxLayout()
            layout_idTime = QHBoxLayout()
            layout_connection = QVBoxLayout()
            layout_connection_icon = QHBoxLayout()
            layout_connection_label = QHBoxLayout()
            layout_up = QHBoxLayout()
            layout_all = QVBoxLayout()

            layout_idTime.addWidget(self.id_label)
            layout_idTime.addStretch(4)
            layout_idTime.addWidget(self.time_label)
            layout_idTime.addStretch(1)

            layout_title.addLayout(layout_idTime)

            layout_connection.addLayout(layout_connection_icon)
            layout_connection.addLayout(layout_connection_label)

            #layout_connection_icon.addSpacing(5)
            layout_connection_icon.addWidget(self.wifi_icon)
            layout_connection_icon.addWidget(self.hw_icon)
            layout_connection_icon.addWidget(self.web_icon)

            #layout_connection_label.addSpacing(10)
            layout_connection_label.addWidget(self.wifi_label)
            layout_connection_label.addWidget(self.hw_label)
            layout_connection_label.addWidget(self.web_label)
            #layout_connection_label.addSpacing(55)

            layout_up.addLayout(layout_title)
            layout_up.addLayout(layout_connection)
            layout_up.addSpacing(20)
            layout_up.addWidget(self.delay_button)
            layout_up.addWidget(self.max_button)
            layout_up.addWidget(self.close_button)

            layout_all.addLayout(layout_up)
            layout_all.addWidget(self.tabWidget)

            self.setLayout(layout_all)
            self.setStyleSheet(self.style_sheet)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

    def initSignal(self):
        try:
            global login
            login = Signals()
            self.tabWidget.currentChanged.connect(self.loginCheckAndIconUpdate)
            self.tab_monitor.wifi_signal.connect(self.setWifiConnected)
            self.tab_monitor.wifi_fail.connect(self.setWifiFailed)
            self.tab_monitor.webService_signal.connect(self.setWebConnected)
            self.tab_monitor.webService_fail.connect(self.setWebFailed)
            self.tab_monitor.hw_signal.connect(self.setHwConnected)
            self.tab_monitor.hw_fail.connect(self.setHwFailed)
            login.login_signal.connect(self.moveToSetting)
            self.delay_button.clicked.connect(self.DelayButtonClicked)
            self.max_button.clicked.connect(self.popMonitorShow)
            self.id_label.clicked.connect(self.waitingMonitorShow)
            self.close_button.clicked.connect(self.close)
            self.wifi_icon.clicked.connect(self.wifiButtonClicked)
            self.hw_icon.clicked.connect(self.hwiconClicked)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def checkWifiConnected(self):
        try:
            cmd = ['iwconfig']
            data = subprocess.check_output(cmd)
            data = data.decode('UTF-8')
            data = data.split("wlan0")

            LANCHECK = ["ifconfig"]

            landata = subprocess.check_output(LANCHECK)
            landata = landata.decode('UTF-8')
            landata = landata.split("eth0")

            if Main.webservice_flag == 0:
                Main.wifi_status = 1
                self.wifi_label.setText("   Not Used")
                self.wifi_label.setStyleSheet("color : #3bd6c6;")
            else :
                if "off/any" in data[1]:
                    if "flags=4163" in landata[1]:
                        Main.wifi_status = 1
                        self.wifi_label.setText("Eth Connected")
                        self.wifi_label.setStyleSheet("color : #3bd6c6;")
                    else:
                        Main.wifi_status = 0
                        self.wifi_label.setText(" Not Connected")
                        self.wifi_label.setStyleSheet("color : red;")
                else:
                    data = data[1].split("Frequency:")
                    id = data[0]
                    fre = data[1][0:2]
                    id = id.split("ESSID:")
                    id = id[1]
                    id = id.strip()
                    id = id.split()
                    id = id[0]

                    if id == 'off/any' :
                        Main.wifi_status = 0
                        self.wifi_label.setText(" Not Connected")
                        self.wifi_label.setStyleSheet("color : red;")
                    else:
                        Main.wifi_status = 1
                        if fre == "5.":
                            self.wifi_label.setText("  {} - 5G".format(id))
                        elif fre == "2.":
                            self.wifi_label.setText("  {} - 2.4G".format(id))
                        else:
                            self.wifi_label.setText("  {}".format(id))
                        self.wifi_label.setStyleSheet("color : #3bd6c6;")
            
            self.tab_monitor.wifi_signal_func(Main.wifi_status)
            
            #[240620_SeokJu.Yang_Add idLabelBackColor(if (QA_Alarm == 1) color changed red)
            self.config = Config('config_th.ini', debug=False)
            self.qa_alarm_id_label_red = self.config.getValue("Setting", "QA_Alarm")
            
            if self.qa_alarm_id_label_red == 1:
                Main.idLabelBackColor = "red"
                Main.idLabelColor = "red"
                self.id_label.setStyleSheet(f"font : 8pt bold; color : white; background-color: red; border : none;")
            elif self.qa_alarm_id_label_red == 0:
                Main.idLabelBackColor = "#325d79"
                Main.idLabelColor = "white"
                self.id_label.setStyleSheet(f"font : 8pt bold; color : white; background-color: #325d79; border : none;")
            #]240620_SeokJu.Yang_Add idLabelBackColor(if (QA_Alarm == 1) color changed red) 
            # self.config = Config('config_th.ini', debug=False)
            # self.update_ver = self.config.getValue("Setting", "update_ver")
            # if self.update_ver == 1:
            #     self.update_timer = QTimer(self)
            #     self.update_timer.setInterval(60000)
            #     self.update_timer.timeout.connect(self.reboot_raspberrypi)
            #     self.update_timer.start()
            #     QMessageBox.information(self,"UPDATE","             Updated Version exists\nProgram will be reboot after 1 minute")
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def reboot_raspberrypi(self):
        try:
            self.config = Config('config_th.ini', debug=False)
            self.config.setValue("Setting","update_ver",0)
            self.config.save()
            subprocess.run(["sudo","reboot"])
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
    def curTimeDisplay(self):
        try:
            sender = self.sender()
            currentTime = time.strftime("%X", time.localtime(time.time()))

            if id(sender) == id(self.timer_curTime):
                Main.currentTime = currentTime
                self.time_label.setText("{}".format(currentTime))
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def hwiconClicked(self):
        try:
            self.config = Config('config_th.ini', debug=False)
            self.sendid = self.config.getValue('Setting', 'id')
            self.serial_number = self.config.getValue('Setting', 'serial_number')
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect(("pwnbit.kr",443))
            sock.settimeout(None)
            send_ip_title = "RPI IP"
            send_ip_text = f"ID : {self.sendid}\nIP : {sock.getsockname()[0]} \nSerial Number : {self.serial_number}"
            smtp.Send_Mail(3, send_ip_title, send_ip_text)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

    def DelayButtonClicked(self):
        try:
            self.config = Config('config_th.ini', debug=False)
            self.delaytime_mode = self.config.getValue("Setting", "delaytime_mode")
            self.delay_mode = self.config.getValue("Setting", "delay_mode")
            if self.delaytime_mode == 1 and Main.delay_flag == 2:
                print("Delay Button Click!")
                if Main.current_timer is not None and Main.current_timer.is_alive() == False:
                    Main.current_timer = None
                Main.delay_flag = 0
                controlGPIO(red_pin, 0)
                if Main.hw_status == 1 and Main.wifi_status == 1 :
                    controlGPIO(yellow_pin,0)
                    controlGPIO(green_pin,1)
                else :
                    controlGPIO(green_pin, 0)
                    controlGPIO(yellow_pin, 1)
                controlGPIO(buzzer_pin,0)
            if self.delaytime_mode == 1 and self.delay_mode == 0:
                if Main.current_timer is not None and Main.current_timer.is_alive() == False:
                    Main.current_timer = None
                Main.delay_flag_Ndelay = 1
                controlGPIO(red_pin, 0)
                if Main.hw_status == 1 and Main.wifi_status == 1 :
                    controlGPIO(yellow_pin,0)
                    controlGPIO(green_pin,1)
                else :
                    controlGPIO(green_pin, 0)
                    controlGPIO(yellow_pin, 1)
                controlGPIO(buzzer_pin,0)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
    #############210428 setting tab max button no action#############
    def popMonitorShow(self):
        try:
            self.current_idx = self.tabWidget.currentIndex()
            if self.current_idx == 1 :
                self.monitor = PopMonitor()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    ##################################################################
    
    def waitingMonitorShow(self):
        try:
            self.monitor = Waiting()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
    def setWifiConnected(self):
        try:
            Main.wifi_status = 1
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
    def setWifiFailed(self):
        try:
            Main.wifi_status = 0
        except Exception as e:
            QMessageBox.critical(None, 'Error', str(e), QMessageBox.Ok)
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")    
    
    def setWebConnected(self):
        try:
            Main.web_status = 1
            self.web_label.setText(("  Connected"))
            self.web_label.setStyleSheet("color : #3bd6c6;")
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
    def setWebFailed(self):
        try:
            Main.web_status = 0
            self.web_label.setText(" Not Connected")
            self.web_label.setStyleSheet("color : red;")
        except Exception as e:
            QMessageBox.critical(None, 'Error', str(e), QMessageBox.Ok)
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")    

    def setHwConnected(self):
        try:
            Main.hw_status = 1
            self.hw_label.setText("  Connected")
            self.hw_label.setStyleSheet("color : #3bd6c6;")
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
    def setHwFailed(self):
        try:
            Main.hw_status = 0
            self.hw_label.setText(" Not Connected")
            self.hw_label.setStyleSheet("color : red;")
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def moveToSetting(self):
        try:
            self.tabWidget.setCurrentIndex(self.settingIdx)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def loginCheckAndIconUpdate(self, idx):
        try:
            self.curIdx = idx
            if self.curIdx == self.settingIdx:
                if self.login_flag == 0:
                    self.curIdx = self.loginIdx
                else:
                    self.curIdx = self.settingIdx
                    
            for i in range(3):
                if self.curIdx == i:
                    self.tabWidget.setTabIcon(i, QtGui.QIcon('./icon_th/tab/{}.png'.format(i)))
                else:
                    self.tabWidget.setTabIcon(i, QtGui.QIcon('./icon_th/tab/{}_gray.png'.format(i)))

            if idx == self.settingIdx:
                if self.login_flag == 0:
                    self.tabWidget.setCurrentIndex(self.loginIdx)
                else:
                    self.tabWidget.setCurrentIndex(self.settingIdx)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def wifiButtonClicked(self):
        try:
            self.checkWifiConnected()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def closeEvent(self, event):
        try:
            box = QMessageBox()
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("Exit Program")
            box.setWindowFlags(Qt.WindowStaysOnTopHint)
            box.setText("Are you sure want to exit?")
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            buttonN = box.button(QMessageBox.Yes)
            buttonN.setText("No")
            buttonY = box.button(QMessageBox.No)
            buttonY.setText("Yes")
            box.exec_()

            if box.clickedButton() == buttonY:
                controlGPIO(green_pin, 0)
                controlGPIO(yellow_pin, 0)
                controlGPIO(red_pin, 0)
                controlGPIO(buzzer_pin, 0)
                if Main.current_timer is not None and Main.current_timer.is_alive() == False:
                    Main.current_timer = None
                self.timer_wifi.stop()
                self.tab_monitor.timer_read.stop()
                self.tab_monitor.timer_write.stop()
                event.accept()
                logger.debug("Program Off")
            else:
                event.ignore()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

class Signals(QObject):
    save_signal = pyqtSignal()
    login_signal = pyqtSignal()

    def __init__(self):
        # 여기는 위아래 둘다 print 나옴
        super(Signals, self).__init__()
    
    def configChanged(self):
        try:
            self.save_signal.emit()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def loginSuccess(self):
        try:
            self.login_signal.emit()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
class Login(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.initSignal()
    
    def initUI(self):
        try:
            self.keyboardWidget = KeyboardWidget()
            self.keyboardWidget.hide()
            self.title_label = QLabel("Login for setting")
            self.title_label.setStyleSheet("font : 20pt bold; color : black;")
            self.pw_label = QLabel("Password : ")
            self.pw_label.setStyleSheet("font : 20pt; color : black;")
            self.pw_edit = VKQLineEdit(name="login", mainWindowObj=self)
            self.pw_edit.setAlignment(QtCore.Qt.AlignCenter)
            self.enter_button = QPushButton("Enter")

            layout_pw = QHBoxLayout()
            layout_pw.addStretch(1)
            layout_pw.addWidget(self.pw_label)
            layout_pw.addWidget(self.pw_edit)
            layout_pw.addWidget(self.enter_button)
            layout_pw.addStretch(1)

            layout_all = QVBoxLayout()
            layout_all.addSpacing(20)
            layout_all.addWidget(self.title_label)
            layout_all.addStretch(2)
            layout_all.addLayout(layout_pw)
            layout_all.addStretch(3)

            self.setAutoFillBackground(True)
            p = self.palette()
            p.setColor(self.backgroundRole(), QColor("#f1e6c1"))
            self.setPalette(p)

            self.setLayout(layout_all)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

    def initSignal(self):
        try:
            self.enter_button.clicked.connect(self.enterButtonClicked)
            self.pw_edit.returnPressed.connect(self.enterButtonClicked)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def enterButtonClicked(self):
        try:
            self.config = Config('config_th.ini', debug=False)
            self.set_pw = self.config.getValue('Setting', 'pw')
            global login
            if str(self.pw_edit.text()) == str(self.set_pw) or str(self.pw_edit.text()) == "5255":
                Main.login_flag = 1
                login.loginSuccess()
                Main.login_flag = 0
                self.pw_edit.clear()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
class Waiting(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.setWindowFlags(Qt.Dialog)
        self.showFullScreen()
        self.setAutoFillBackground(True)
        p = self.palette()
        p.setColor(self.backgroundRole(), QColor("#325d79"))
        self.setPalette(p)
        self.showFullScreen()
    
    def initUI(self):
        try:
            self.title_label = QLabel(f"{Main.set_id}")
            #[240620_SeokJu.Yang_Add idLabelBackColor(if (QA_Alarm == 1) color changed red)
            self.title_label.setStyleSheet(f"font : 60pt bold; color : {Main.idLabelColor};")
            #[240620_SeokJu.Yang_Add idLabelBackColor(if (QA_Alarm == 1) color changed red)
            self.layout_title = QHBoxLayout()
            self.layout_title.addStretch(1)
            self.layout_title.addWidget(self.title_label)
            self.layout_title.addStretch(1)
            
            self.layout_all = QVBoxLayout()
            self.layout_all.addStretch(1)
            self.layout_all.addLayout(self.layout_title)
            self.layout_all.addStretch(1)

            self.setAutoFillBackground(True)
            p = self.palette()
            p.setColor(self.backgroundRole(), QColor("#f1e6c1"))
            self.setPalette(p)

            self.setLayout(self.layout_all)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
    def mousePressEvent(self, event):
        try:
            self.close()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

class Monitor(QWidget):
    label_fontSize = 7
    wifi_signal = pyqtSignal()
    wifi_fail = pyqtSignal()
    hw_signal = pyqtSignal()
    hw_fail = pyqtSignal()
    webService_signal = pyqtSignal()
    webService_fail = pyqtSignal()
    style_sheet = """
    """
    rs485 = RS485Event()
    
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Dialog)
        self.config = Config('config_th.ini', debug=False)
        self.initUI()
        self.initSignal()
        self.setConfig()
        self.timeOutRead()
    
    def wifi_signal_func(self, status):
        if status == 1:
            self.wifi_signal.emit()
        else:
            self.wifi_fail.emit()
    
    def initUI(self):
        try:
            global display_left, display_right
            self.id_label = QPushButton("")
            #self.id_label.setFlat(True)

            # Widgets & Layouts List For 8 Channel
            self.frame_humid_list = []
            self.gb_list = []
            self.temp_label_list = []
            self.humid_label_list = []

            self.temp_icon_list = []
            self.humid_icon_list = []

            self.temp_lcd_list = []
            self.humid_lcd_list = []
            self.temp_pbar_list = []
            self.humid_pbar_list = []
            self.frame_temp_list = []
            self.layout_temp_list = []
            self.layout_temp_L_list = []
            self.layout_tempd_L_up_list = []
            self.layout_temp_R_list = []
            self.layout_humid_L_list = []
            self.layout_humid_L_up_list = []
            self.layout_humid_R_list = []
            self.layout_humid_list = []
            self.layout_channel_list = []

            for i in range(8):
                myTempFrame = QFrame()
                myHumidFrame = QFrame()
                myGb = QGroupBox('  Channel : {}  '.format(i + 1))
                myTempLabel = QLabel("Temperature[ °C ]")
                myHumidLabel = QLabel("Humidity  [ % ]")
                myTempIcon = QPushButton('')
                myHumidIcon = QPushButton('')
                myTempLcd = QLCDNumber()
                myHumidLcd = QLCDNumber()
                myTempPbar = QProgressBar()
                myTempPbar.setOrientation(QtCore.Qt.Vertical)
                myTempPbar.setTextVisible(False)
                myHumidPbar = QProgressBar()
                myHumidPbar.setOrientation(QtCore.Qt.Vertical)
                myHumidPbar.setTextVisible(False)
                # Layout
                myTempLLayout = QVBoxLayout()
                myTempRLayout = QVBoxLayout()
                myHumidLLayout = QVBoxLayout()

                myTempLUpLayout = QHBoxLayout()
                myHumidLUpLayout = QHBoxLayout()

                myHumidRLayout = QVBoxLayout()
                myTempLayout = QHBoxLayout()
                myHumidLayout = QHBoxLayout()
                myChannelLayout = QHBoxLayout()

                self.frame_temp_list.append(myTempFrame)
                self.frame_humid_list.append(myHumidFrame)
                self.gb_list.append(myGb)
                self.temp_label_list.append(myTempLabel)
                self.humid_label_list.append(myHumidLabel)
                self.temp_icon_list.append(myTempIcon)
                self.humid_icon_list.append(myHumidIcon)
                self.temp_lcd_list.append(myTempLcd)
                self.humid_lcd_list.append(myHumidLcd)
                self.temp_pbar_list.append(myTempPbar)
                self.humid_pbar_list.append(myHumidPbar)
                # Layout
                self.layout_tempd_L_up_list.append(myTempLUpLayout)
                self.layout_temp_L_list.append(myTempLLayout)
                self.layout_temp_R_list.append(myTempRLayout)
                self.layout_humid_L_up_list.append(myHumidLUpLayout)
                self.layout_humid_L_list.append(myHumidLLayout)
                self.layout_humid_R_list.append(myHumidRLayout)
                self.layout_temp_list.append(myTempLayout)
                self.layout_humid_list.append(myHumidLayout)
                self.layout_channel_list.append(myChannelLayout)

                # Set Layout
                self.layout_tempd_L_up_list[i].addWidget(self.temp_label_list[i])
                # self.layout_tempd_L_up_list[i].addWidget(self.temp_icon_list[i])
                self.layout_temp_L_list[i].addLayout(self.layout_tempd_L_up_list[i])
                self.layout_temp_L_list[i].addWidget(self.temp_icon_list[i])
                self.layout_temp_R_list[i].addWidget(self.temp_lcd_list[i])
                self.layout_temp_list[i].addLayout(self.layout_temp_L_list[i])
                self.layout_temp_list[i].addLayout(self.layout_temp_R_list[i])

                self.layout_humid_L_up_list[i].addWidget(self.humid_label_list[i])
                # self.layout_humid_L_up_list[i].addWidget(self.humid_icon_list[i])
                self.layout_humid_L_list[i].addLayout(self.layout_humid_L_up_list[i])
                self.layout_humid_L_list[i].addWidget(self.humid_icon_list[i])
                self.layout_humid_R_list[i].addWidget(self.humid_lcd_list[i])
                self.layout_humid_list[i].addLayout(self.layout_humid_L_list[i])
                self.layout_humid_list[i].addLayout(self.layout_humid_R_list[i])

                self.frame_temp_list[i].setLayout(self.layout_temp_list[i])
                self.frame_humid_list[i].setLayout(self.layout_humid_list[i])
                self.layout_channel_list[i].addWidget(self.frame_temp_list[i])
                self.layout_channel_list[i].addWidget(self.frame_humid_list[i])
                self.gb_list[i].setLayout(self.layout_channel_list[i])
                
            self.config = Config('config_th.ini', debug=False)
            self.disp_mode = self.config.getValue('Setting', 'disp_mode')
            if  self.disp_mode == 0 :
                display_left = 0
                display_right = 1
            elif self.disp_mode == 1 :
                display_left = 1
                display_right = 0
            else :
                display_left = 0
                display_right = 1
            
            self.layout_all = QGridLayout()
            self.layout_all.addWidget(self.gb_list[0], 0, display_left)
            self.layout_all.addWidget(self.gb_list[1], 1, display_left)
            self.layout_all.addWidget(self.gb_list[2], 2, display_left)
            self.layout_all.addWidget(self.gb_list[3], 3, display_left)
            
            self.layout_all.addWidget(self.gb_list[4], 0, display_right)
            self.layout_all.addWidget(self.gb_list[5], 1, display_right)
            self.layout_all.addWidget(self.gb_list[6], 2, display_right)
            self.layout_all.addWidget(self.gb_list[7], 3, display_right)

            self.setLayout(self.layout_all)
            self.setStyleSheet(self.style_sheet)

            self.setAutoFillBackground(True)
            p = self.palette()
            p.setColor(self.backgroundRole(), QColor("#f1e6c1"))
            self.setPalette(p)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

    def initSignal(self):
        try:
            global signals
            signals = Signals()
            signals.save_signal.connect(self.initConfig)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def initConfig(self):
        self.setConfig_save()
    
    def initStyle(self, onList):
        try:
            for idx, item in enumerate(self.frame_temp_list):
                if idx in onList:
                    item.setFrameShape(QFrame.StyledPanel)
                    item.setStyleSheet("background-color: #ffffff;")
                else:
                    item.setStyleSheet("background-color: #636e72; border: 1px solid #636e72;")

            for idx, item in enumerate(self.frame_humid_list):
                if idx in onList:
                    item.setStyleSheet("background-color: #ffffff;")
                    item.setFrameShape(QFrame.StyledPanel)
                else:
                    item.setStyleSheet("background-color: #636e72; border: 1px solid #636e72;")

            for idx, item in enumerate(self.temp_label_list):
                if idx in onList:
                    item.setStyleSheet("font : 7pt; color : black;")
                else:
                    item.setStyleSheet("font : 7pt; color : #636e72; background-color: #636e72;")

            for idx, item in enumerate(self.humid_label_list):
                if idx in onList:
                    item.setStyleSheet("font : 7pt; color : black;")

                else:
                    item.setStyleSheet("font : 7pt; color : #636e72; background-color: #636e72;")

            for idx, item in enumerate(self.temp_lcd_list):
                if idx in onList:
                    item.setSegmentStyle(QLCDNumber.Flat)
                    item.setStyleSheet("border-image: url(green.jpg);")
                else:
                    item.display("")
                    item.setStyleSheet("background-color : #636e72;")

            for idx, item in enumerate(self.humid_lcd_list):
                if idx in onList:
                    item.setSegmentStyle(QLCDNumber.Flat)
                    item.setStyleSheet("border-image: url(blue.jpg);")
                else:
                    item.display("")
                    item.setStyleSheet("background-color : #636e72;")

            for idx, item in enumerate(self.gb_list):
                if idx in onList:
                    item.setObjectName("ColoredGroupBox")
                    item.setStyleSheet(
                        "QGroupBox#ColoredGroupBox { border: 1px solid black; font-size: 9px; font-weight: bold; margin-top: 1ex; color :black;}"
                        "QGroupBox::title{subcontrol-origin: margin; subcontrol-position: top center;}")
                else:
                    item.setObjectName("ColoredGroupBox")
                    item.setStyleSheet(
                        "QGroupBox#ColoredGroupBox {background-color:#636e72; border: 1px solid #636e72; font-size: 1px; font-weight: bold; margin-top: 1ex; color :#1c4e80;}"
                        "QGroupBox::title{subcontrol-origin: margin; subcontrol-position: top center;}")

            for idx, item in enumerate(self.temp_icon_list):
                if idx in onList:
                    item.setFlat(True)
                    item.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
                    item.setStyleSheet("""
                                qproperty-icon: url("./icon_th/temperature.png"); /* empty image */
                                qproperty-iconSize: 22px 18px; 
                                background-color:#ffffff;
                                """)
                else:
                    item.setFlat(True)
                    item.setStyleSheet("""
                                qproperty-icon: url("./icon_th/remov3e.png"); /* empty image */
                                qproperty-iconSize: 22px 18px; /* space for the background image */
                                background-color:#636e72;
                                """)

            for idx, item in enumerate(self.humid_icon_list):
                if idx in onList:
                    item.setFlat(True)
                    item.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
                    item.setStyleSheet("""
                                qproperty-icon: url("./icon_th/humidity.png"); /* empty image */
                                qproperty-iconSize: 22px 18px; 
                                background-color:#ffffff;
                                """)
                else:
                    item.setFlat(True)
                    item.setStyleSheet("""
                                qproperty-icon: url("./icon_th/remo1ve.png"); /* empty image */
                                qproperty-iconSize: 22px 18px; /* space for the background image */
                                background-color:#636e72;
                                """)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

    def setConfig(self):
        try:
            # Set values
            self.config = Config('config_th.ini', debug=False)
            self.offset_temp = []
            self.offset_humid = []
            self.temp_min = []
            self.temp_max = []
            self.humid_min = []
            self.humid_max = []
            self.set_on_list = []
            for i in range(8):
                self.offset_temp.append(self.config.getValue(str(i + 1), 'offset_temp'))
                self.offset_humid.append(self.config.getValue(str(i + 1), 'offset_humid'))
                self.temp_min.append(self.config.getValue(str(i + 1), 'temp_min'))
                self.temp_max.append(self.config.getValue(str(i + 1), 'temp_max'))
                self.humid_min.append(self.config.getValue(str(i + 1), 'humid_min'))
                self.humid_max.append(self.config.getValue(str(i + 1), 'humid_max'))
                self.set_on_list.append(int(self.config.getValue(str(i + 1), 'on')))
            
            if Main.setconfig_flag == 0:
                Main.setconfig_flag = 1
                self.read_interval = self.config.getValue('Setting', 'read_interval')
                self.write_interval = self.config.getValue('Setting', 'write_interval')

                self.timer_read = QTimer(self)
                self.timer_read.setInterval(1000 * self.read_interval)  # milsec -> sec
                self.timer_read.timeout.connect(self.timeOutRead)
                self.timer_read.start()
            
                self.timer_write = QTimer(self)
                self.timer_write.setInterval(60000 * self.write_interval)  # milsec -> min
                self.timer_write.timeout.connect(self.timeOutWrite)
                self.timer_write.start()
                
                #[250909_SeokJu.Yang_add alive check timer
                self.aliveCheckTimer = QTimer(self)
                self.aliveCheckTimer.setInterval(3000)
                self.aliveCheckTimer.timeout.connect(self.AliveCheck)
                self.aliveCheckTimer.start()
                #]250909_SeokJu.Yang_add alive check timer
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
            
    #[250909_SeokJu.Yang_add alive check timer
    def AliveCheck(self):
        try:
            if not self.timer_read.isActive():
                logger.debug("self.timer_read restart")
                self.timer_read.start()
            if not self.timer_write.isActive():
                logger.debug("self.timer_write restart")
                self.timer_write.start()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    #]250909_SeokJu.Yang_add alive check timer
            
            
    def setConfig_save(self):
        try:
            # Set values
            self.config = Config('config_th.ini', debug=False)
            self.offset_temp = []
            self.offset_humid = []
            self.temp_min = []
            self.temp_max = []
            self.humid_min = []
            self.humid_max = []
            self.set_on_list = []
            for i in range(8):
                self.offset_temp.append(self.config.getValue(str(i + 1), 'offset_temp'))
                self.offset_humid.append(self.config.getValue(str(i + 1), 'offset_humid'))
                self.temp_min.append(self.config.getValue(str(i + 1), 'temp_min'))
                self.temp_max.append(self.config.getValue(str(i + 1), 'temp_max'))
                self.humid_min.append(self.config.getValue(str(i + 1), 'humid_min'))
                self.humid_max.append(self.config.getValue(str(i + 1), 'humid_max'))
                self.set_on_list.append(int(self.config.getValue(str(i + 1), 'on')))
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def getDataFromSensor(self):
        try:
            self.connected_flag = 1
            self.config = Config('config_th.ini', debug=False)
            
            try:
                self.rs485.open()
            except Exception as e:
                pass
            
            self.tca = multiplexer.TCA9548A('I2C switch 0', 0x70, 1)

            self.value_temp = [0, 0, 0, 0, 0, 0, 0, 0]
            self.value_humid = [0, 0, 0, 0, 0, 0, 0, 0]
            self.enable_ch = []
            self.disable_ch = []
            for idx, onOff in enumerate(self.set_on_list):
                if onOff == 1:
                    self.enable_ch.append(idx)
                elif onOff == 0:
                    self.disable_ch.append(idx)
            
            self.offset_temp = []
            self.offset_humid = []
            self.humid_min = []
            self.humid_max = []
            self.humid_offset = self.config.getValue('Setting', 'humidoffset')
            self.humid_offset_all = int(self.humid_offset) # Humid min, max control
            self.board_check = self.config.getValue('Setting', 'board_mode')
            self.pin_check = self.config.getValue('Setting', 'pin_mode')

            for i in range(8):
                self.offset_temp.append(self.config.getValue(str(i + 1), 'offset_temp'))
                self.offset_humid.append(self.config.getValue(str(i + 1), 'offset_humid'))
                self.humid_min.append(self.config.getValue(str(i + 1), 'humid_min'))
                self.humid_max.append(self.config.getValue(str(i + 1), 'humid_max'))
            
            for idx in self.enable_ch:
                try:
                    # SHT21 check
                    self.tca.chn(idx)
                    data = sensor.SHT21(self.tca.bus) # ex) data = <sensor.SHT21 object at 0x65c65850>
                    temp = data.read_temperature()
                    humid = data.read_humidity()
                    self.value_temp[idx] = round(temp, 1)
                    self.value_humid[idx] = round(humid, 1)
                except:
                    self.connected_flag = 0
                
                # (N2 input) when serial port is open
                if self.board_check == 1:
                    try:
                        if (self.value_humid[idx] + self.offset_humid[idx]) >= (self.humid_max[idx] - self.humid_offset_all):
                            self.rs485.write((idx, 1))
                            logger.debug(f"Channel {idx + 1} : N2 On(Humid : {round(self.value_humid[idx] + self.offset_humid[idx],1)})")
                            print(f"**N2 On** Channel {idx + 1} / Humid : {round(self.value_humid[idx] + self.offset_humid[idx],1)}")
                        elif (self.value_humid[idx] + self.offset_humid[idx]) <= (self.humid_min[idx] + self.humid_offset_all):
                            self.rs485.write((idx, 0))
                            logger.debug(f"Channel {idx + 1} : N2 Off(Humid : {round(self.value_humid[idx] + self.offset_humid[idx],1)})")
                            print(f"**N2 Off** Channel {idx + 1} / Humid : {round(self.value_humid[idx] + self.offset_humid[idx],1)}")
                    except Exception as e:
                        self.connected_flag = 0
                    
                # (N2 input) when serial port is not open
                elif self.pin_check == 1:
                    try:
                        if idx < 4 and (self.value_humid[idx] + self.offset_humid[idx]) >= (self.humid_max[idx] - self.humid_offset_all):
                            if idx == 0:
                                controlGPIO(out1_pin, 1)
                            elif idx == 1:
                                controlGPIO(out2_pin, 1)
                            elif idx == 2:
                                controlGPIO(out3_pin, 1)
                            elif idx == 3:
                                controlGPIO(out4_pin, 1)
                            logger.debug(f"Channel {idx + 1} : N2 On(Humid : {round(self.value_humid[idx] + self.offset_humid[idx],1)})")
                        elif idx < 4 and (self.value_humid[idx] + self.offset_humid[idx]) <= (self.humid_min[idx] + self.humid_offset_all):
                            if idx == 0:
                                controlGPIO(out1_pin, 0)
                            elif idx == 1:
                                controlGPIO(out2_pin, 0)
                            elif idx == 2:
                                controlGPIO(out3_pin, 0)
                            elif idx == 3:
                                controlGPIO(out4_pin, 0)
                                logger.debug(f"Channel {idx + 1} : N2 Off(Humid : {round(self.value_humid[idx] + self.offset_humid[idx],1)})")
                    except Exception as e:
                        logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
                try:
                    if (self.value_humid[idx] + self.offset_humid[idx]) >= (self.humid_max[idx] - self.humid_offset_all) or (self.value_temp[idx] + self.offset_temp[idx]) >= (self.temp_max[idx]):
                        logger.debug(f"Channel {idx + 1} : Temp : {round(self.value_temp[idx] + self.offset_temp[idx],1)} / Humid : {round(self.value_humid[idx] + self.offset_humid[idx],1)}")
                    elif (self.value_humid[idx] + self.offset_humid[idx]) <= (self.humid_min[idx] + self.humid_offset_all) or (self.value_temp[idx] + self.offset_temp[idx]) <= (self.temp_min[idx]):
                        logger.debug(f"Channel {idx + 1} : Temp : {round(self.value_temp[idx] + self.offset_temp[idx],1)} / Humid : {round(self.value_humid[idx] + self.offset_humid[idx],1)}")
                except Exception as e:
                    logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            try:
                self.rs485.close()
            except:
                print('rs485 is not open')
                
            for idx in self.disable_ch:
                self.value_temp[idx] = 0
                self.value_humid[idx] = 0
            if self.connected_flag == 1:
                self.hw_signal.emit()
            else:
                self.hw_fail.emit()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

    def displayData(self):
        try:
            for i in self.enable_ch:
                self.value_temp[i] = self.value_temp[i] + self.offset_temp[i]
                self.value_humid[i] = self.value_humid[i] + self.offset_humid[i]
                # 201105_ humid value is not zero
                if self.value_humid[i] < 0 :
                    self.value_humid[i] = 0
                self.temp_lcd_list[i].display(self.value_temp[i])
                self.humid_lcd_list[i].display(self.value_humid[i])

            self.initStyle(self.enable_ch)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

    def timeOutRead(self):
        try:
            self.getDataFromSensor()
            self.displayData()
            self.config = Config('config_th.ini', debug=False)
            self.delay_mode = self.config.getValue("Setting",'delay_mode')
            if self.delay_mode == 1:
                self.checkOver()
            elif self.delay_mode == 0:
                self.checkOver_Ndelay()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

    def timeOutWrite(self):
        self.sendDataToWeb()
    
    def sendDataToWeb(self):
        try:
            if Main.webservice_flag == 1:
                self.config = Config('config_th.ini', debug=False)
                self.webservice_data = self.config.getValue('Setting', 'weblist')
                
                # if weblist input only number : int => tuple
                if type(self.webservice_data) == int:
                    self.webservice_data = (self.webservice_data,)
                    
                self.webservice_index = list(self.webservice_data)
                self.senddata_temp = ""
                self.senddata_humid = ""
                
                for i in self.webservice_index:
                    self.senddata_temp += (str(round(self.value_temp[i-1],1)) + ',')
                    self.senddata_humid += (str(round(self.value_humid[i-1],1)) + ',')
                self.senddata_temp = self.senddata_temp[:-1]
                self.senddata_humid = self.senddata_humid[:-1]

                if Main.wifi_status == 1:
                    self.config = Config('config_th.ini', debug=False)
                    self.set_id = self.config.getValue('Setting', 'id')
                    URL = "http://cim_service.amkor.co.kr:8080/ysj/smshelf/inputControllerValue"
                    params = {
                        'shelfNo': '{}'.format(self.set_id),
                        'temperature': self.senddata_temp,
                        'humidity': self.senddata_humid,
                        'lang': 1
                    }
                    self.value_sum = "Web Data" + ">" + "temp : " + self.senddata_temp + " " + "humid : " + self.senddata_humid
                    try:
                        res = requests.get(url=URL, params=params, verify=False)
                        if res.status_code == 200:
                            self.webService_signal.emit()
                            logger.debug(f"webservice success : {self.value_sum}")
                        else:
                            self.webService_fail.emit()
                            logger.debug("webservice fail")
                    except Exception as e:
                        self.webService_fail.emit()
                        logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
                else:
                    self.webService_fail.emit()
            else:
                self.webService_signal.emit()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
    def checkOver(self):
        try:
            self.over_flag_delayon = 0
            for i, min in enumerate(self.temp_min):
                if min > self.value_temp[i] and i in self.enable_ch:
                    self.frame_temp_list[i].setStyleSheet("background-color: red;")
                    self.temp_label_list[i].setStyleSheet("background-color: red; font-size:%dpx" % self.label_fontSize)
                    self.over_flag_delayon = 1
            for i, max in enumerate(self.temp_max):
                if max < self.value_temp[i] and i in self.enable_ch:
                    self.frame_temp_list[i].setStyleSheet("background-color: red;")
                    self.temp_label_list[i].setStyleSheet("background-color: red; font-size:%dpx" % self.label_fontSize)
                    self.over_flag_delayon = 1
            for i, max in enumerate(self.humid_max):
                if max < self.value_humid[i] and i in self.enable_ch:
                    self.frame_humid_list[i].setStyleSheet("background-color: red;")
                    self.humid_label_list[i].setStyleSheet("background-color: red; font-size:%dpx" % self.label_fontSize)
                    self.over_flag_delayon = 1
            if self.over_flag_delayon == 1 and Main.delay_flag == 0:
                Main.delay_flag = 1
                self.config = Config('config_th.ini', debug=False)
                self.delay_time = self.config.getValue('Setting', 'delay_time')
                Main.current_timer = threading.Timer(self.delay_time, self.alert_delay)
                Main.current_timer.start()
                print("Delay Timer Start")
            elif self.over_flag_delayon == 1 and Main.delay_flag == 2:
                controlGPIO(green_pin, 0)
                controlGPIO(yellow_pin, 0)
                controlGPIO(red_pin, 1)
                controlGPIO(buzzer_pin,1)
            elif self.over_flag_delayon == 0 and Main.delay_flag == 2:
                Main.delay_flag = 0
                controlGPIO(red_pin, 0)
                if Main.hw_status == 1 and Main.wifi_status == 1:
                    controlGPIO(yellow_pin, 0)
                    controlGPIO(green_pin, 1)
                else:
                    controlGPIO(green_pin, 0)
                    controlGPIO(yellow_pin, 1)
                controlGPIO(buzzer_pin, 0)
            else:
                controlGPIO(red_pin, 0)
                if Main.hw_status == 1 and Main.wifi_status == 1:
                    controlGPIO(yellow_pin, 0)
                    controlGPIO(green_pin, 1)
                else:
                    controlGPIO(green_pin, 0)
                    controlGPIO(yellow_pin, 1)
                controlGPIO(buzzer_pin, 0)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

    def alert_delay(self):
        try:
            self.config = Config('config_th.ini', debug=False)
            self.delay_mode = self.config.getValue('Setting', 'delay_mode')
            if self.delay_mode == 1:
                Main.delay_flag = 2
            elif self.delay_mode == 0:
                Main.delay_flag_Ndelay = 0
            if Main.current_timer is not None and Main.current_timer.is_alive() == False:
                Main.current_timer = None
            print("alert delay")
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def checkOver_Ndelay(self):
        try:            
            self.over_flag_delayoff = 0
            for i, min in enumerate(self.temp_min):
                if min > self.value_temp[i] and i in self.enable_ch:
                    self.frame_temp_list[i].setStyleSheet("background-color: red;")
                    self.temp_label_list[i].setStyleSheet("background-color: red; font-size:%dpx" % self.label_fontSize)
                    self.over_flag_delayoff = 1
            for i, max in enumerate(self.temp_max):
                if max < self.value_temp[i] and i in self.enable_ch:
                    self.frame_temp_list[i].setStyleSheet("background-color: red;")
                    self.temp_label_list[i].setStyleSheet("background-color: red; font-size:%dpx" % self.label_fontSize)
                    self.over_flag_delayoff = 1
            for i, max in enumerate(self.humid_max):
                if max < self.value_humid[i] and i in self.enable_ch:
                    self.frame_humid_list[i].setStyleSheet("background-color: red;")
                    self.humid_label_list[i].setStyleSheet("background-color: red; font-size:%dpx" % self.label_fontSize)
                    self.over_flag_delayoff = 1
            if self.over_flag_delayoff == 1 and Main.delay_flag_Ndelay == 1:
                Main.delay_flag_Ndelay = 2
                self.config = Config('config_th.ini', debug=False)
                self.delay_time = self.config.getValue('Setting', 'delay_time')
                Main.current_timer = threading.Timer(self.delay_time, self.alert_delay)
                Main.current_timer.start()
                print("Delay Timer Start")
            elif self.over_flag_delayoff == 1 and Main.delay_flag_Ndelay == 0:
                controlGPIO(green_pin, 0)
                controlGPIO(yellow_pin, 0)
                controlGPIO(red_pin, 1)
                controlGPIO(buzzer_pin,1)
            else:
                controlGPIO(red_pin, 0)
                if Main.hw_status == 1 and Main.wifi_status == 1:
                    controlGPIO(yellow_pin, 0)
                    controlGPIO(green_pin, 1)
                else:
                    controlGPIO(green_pin, 0)
                    controlGPIO(yellow_pin, 1)
                controlGPIO(buzzer_pin, 0)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

class PopMonitor(Monitor):
    one_flag = 0
    
    def __init__(self):
        super().__init__()
        
        self.config = Config('config_th.ini', debug=False)
        self.read_interval = self.config.getValue('Setting', 'read_interval')

        self.timer_read2 = QTimer(self)
        self.timer_read2.setInterval(1000 * self.read_interval)  # milsec -> sec
        self.timer_read2.timeout.connect(self.timeOutRead)
        self.timer_read2.start()
        
        self.timer_curTime = QTimer(self)
        self.timer_curTime.setInterval(10000)
        self.timer_curTime.timeout.connect(self.curTimeDisplay)
        self.timer_curTime.start()
        
        #[250909_SeokJu.Yang_add alive check timer
        self.aliveCheckTimer = QTimer(self)
        self.aliveCheckTimer.setInterval(3000)
        self.aliveCheckTimer.timeout.connect(self.AliveCheck)
        self.aliveCheckTimer.start()
        #]250909_SeokJu.Yang_add alive check timer
        
        self.showFullScreen()
        self.setAutoFillBackground(True)
        p = self.palette()
        p.setColor(self.backgroundRole(), QColor("#325d79"))
        self.setPalette(p)
        self.showFullScreen()
        self.config = Config('config_th.ini', debug=False)
        self.delaytime_mode = self.config.getValue("Setting", "delaytime_mode")
       
    #[250909_SeokJu.Yang_add alive check timer
    def AliveCheck(self):
        try:
            if not self.timer_read2.isActive():
                logger.debug("self.timer_read2 restart")
                self.timer_read2.start()
            if not self.timer_curTime.isActive():
                logger.debug("self.timer_curTime restart")
                self.timer_curTime.start()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    #]250909_SeokJu.Yang_add alive check timer
        
    def closeEvent(self, event):
        try:
            self.timer_read2.stop()
            self.timer_read2.deleteLater()
            self.timer_curTime.stop()
            self.timer_curTime.deleteLater()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
        
    def initSignal(self):
        try:
            self.delay_icon.clicked.connect(self.DelayButtonClicked2)
            self.hw_icon.clicked.connect(self.hwiconClicked2)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def hwiconClicked2(self):
        try:
            self.config = Config('config_th.ini', debug=False)
            self.sendid = self.config.getValue('Setting', 'id')
            self.serial_number = self.config.getValue('Setting', 'serial_number')
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect(("pwnbit.kr",443))
            sock.settimeout(None)
            send_ip_title = "RPI IP"
            send_ip_text = f"ID : {self.sendid}\nIP : {sock.getsockname()[0]}\nSerial Number : {self.serial_number}"
            smtp.Send_Mail(3, send_ip_title, send_ip_text)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

    def sendDataToWeb(self):
        pass

    def DelayButtonClicked2(self):
        try:
            self.config = Config('config_th.ini', debug=False)
            self.delaytime_mode = self.config.getValue("Setting", "delaytime_mode")
            self.delay_mode = self.config.getValue("Setting", "delay_mode")
            if self.delaytime_mode == 1 and Main.delay_flag == 2:
                print("Delay Button Click!")
                if Main.current_timer is not None and Main.current_timer.is_alive() == False:
                    Main.current_timer = None
                Main.delay_flag = 0
                controlGPIO(red_pin, 0)
                if Main.hw_status == 1 and Main.wifi_status == 1 :
                    controlGPIO(yellow_pin,0)
                    controlGPIO(green_pin,1)
                else :
                    controlGPIO(green_pin, 0)
                    controlGPIO(yellow_pin, 1)
                controlGPIO(buzzer_pin,0)
            if self.delaytime_mode == 1 and self.delay_mode == 0:
                if Main.current_timer is not None and Main.current_timer.is_alive() == False:
                    Main.current_timer = None
                Main.delay_flag_Ndelay = 1
                controlGPIO(red_pin, 0)
                if Main.hw_status == 1 and Main.wifi_status == 1 :
                    controlGPIO(yellow_pin,0)
                    controlGPIO(green_pin,1)
                else :
                    controlGPIO(green_pin, 0)
                    controlGPIO(yellow_pin, 1)
                controlGPIO(buzzer_pin,0)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def curTimeDisplay(self):
        try:
            sender = self.sender()
            currentTime = time.strftime("%H:%M", time.localtime(time.time()))

            if id(sender) == id(self.timer_curTime):
                Main.currentTime = currentTime
                self.time_label.setText("{}".format(currentTime))
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

    # full display
    def initUI(self):
        try:
            self.config = Config('config_th.ini', debug=False)
            self.set_id = self.config.getValue('Setting', 'id')
            self.id_label = QPushButton(f"ID : {self.set_id}")
            #[240620_SeokJu.Yang_Add idLabelBackColor(if (QA_Alarm == 1) color changed red)
            self.id_label.setStyleSheet(f"font-size: 14px; color : white; background-color: {Main.idLabelBackColor}; border : none")
            #[240620_SeokJu.Yang_Add idLabelBackColor(if (QA_Alarm == 1) color changed red)
            #self.id_label.setFlat(True)
            
            self.time_label = QLabel("")
            self.time_label.setStyleSheet("color : white; font-size:14px;")
            self.wifi_icon = QPushButton("")
            self.wifi_icon.setFlat(True)
            self.hw_icon = QPushButton("")
            self.hw_icon.setFlat(True)
            self.web_icon = QPushButton("")
            self.web_icon.setFlat(True)
            self.delay_icon = QPushButton("")
            self.delay_icon.setFlat(True)

            # Widgets & Layouts List For 8 Channel
            self.frame_humid_list = []
            self.gb_list = []
            self.temp_label_list = []
            self.humid_label_list = []

            self.temp_icon_list = []
            self.humid_icon_list = []

            self.temp_lcd_list = []
            self.humid_lcd_list = []
            self.temp_pbar_list = []
            self.humid_pbar_list = []
            self.frame_temp_list = []
            self.layout_temp_list = []
            self.layout_temp_L_list = []
            self.layout_tempd_L_up_list = []
            self.layout_temp_R_list = []
            self.layout_humid_L_list = []
            self.layout_humid_L_up_list = []
            self.layout_humid_R_list = []
            self.layout_humid_list = []
            self.layout_channel_list = []
            
            for i in range(8):
                myTempFrame = QFrame()
                myHumidFrame = QFrame()
                myGb = QGroupBox('  Channel : {}  '.format(i + 1))
                myTempLabel = QLabel("Temperature[ °C ]")
                myHumidLabel = QLabel("Humidity  [ % ]")
                myTempIcon = QPushButton('')
                myHumidIcon = QPushButton('')
                myTempLcd = QLCDNumber()
                myHumidLcd = QLCDNumber()
                myTempPbar = QProgressBar()
                myTempPbar.setOrientation(QtCore.Qt.Vertical)
                myTempPbar.setTextVisible(False)
                myHumidPbar = QProgressBar()
                myHumidPbar.setOrientation(QtCore.Qt.Vertical)
                myHumidPbar.setTextVisible(False)
                # Layout
                myTempLLayout = QVBoxLayout()
                myTempRLayout = QVBoxLayout()
                myHumidLLayout = QVBoxLayout()

                myTempLUpLayout = QHBoxLayout()
                myHumidLUpLayout = QHBoxLayout()

                myHumidRLayout = QVBoxLayout()
                myTempLayout = QHBoxLayout()
                myHumidLayout = QHBoxLayout()
                myChannelLayout = QHBoxLayout()

                self.frame_temp_list.append(myTempFrame)
                self.frame_humid_list.append(myHumidFrame)
                self.gb_list.append(myGb)
                self.temp_label_list.append(myTempLabel)
                self.humid_label_list.append(myHumidLabel)
                self.temp_icon_list.append(myTempIcon)
                self.humid_icon_list.append(myHumidIcon)
                self.temp_lcd_list.append(myTempLcd)
                self.humid_lcd_list.append(myHumidLcd)
                self.temp_pbar_list.append(myTempPbar)
                self.humid_pbar_list.append(myHumidPbar)
                # Layout
                self.layout_tempd_L_up_list.append(myTempLUpLayout)
                self.layout_temp_L_list.append(myTempLLayout)
                self.layout_temp_R_list.append(myTempRLayout)
                self.layout_humid_L_up_list.append(myHumidLUpLayout)
                self.layout_humid_L_list.append(myHumidLLayout)
                self.layout_humid_R_list.append(myHumidRLayout)
                self.layout_temp_list.append(myTempLayout)
                self.layout_humid_list.append(myHumidLayout)
                self.layout_channel_list.append(myChannelLayout)

                # Set Layout
                self.layout_tempd_L_up_list[i].addWidget(self.temp_label_list[i])
                # self.layout_tempd_L_up_list[i].addWidget(self.temp_icon_list[i])
                self.layout_temp_L_list[i].addLayout(self.layout_tempd_L_up_list[i])
                self.layout_temp_L_list[i].addWidget(self.temp_icon_list[i])
                self.layout_temp_R_list[i].addWidget(self.temp_lcd_list[i])
                self.layout_temp_list[i].addLayout(self.layout_temp_L_list[i])
                self.layout_temp_list[i].addLayout(self.layout_temp_R_list[i])

                self.layout_humid_L_up_list[i].addWidget(self.humid_label_list[i])
                # self.layout_humid_L_up_list[i].addWidget(self.humid_icon_list[i])
                self.layout_humid_L_list[i].addLayout(self.layout_humid_L_up_list[i])
                self.layout_humid_L_list[i].addWidget(self.humid_icon_list[i])
                self.layout_humid_R_list[i].addWidget(self.humid_lcd_list[i])
                self.layout_humid_list[i].addLayout(self.layout_humid_L_list[i])
                self.layout_humid_list[i].addLayout(self.layout_humid_R_list[i])

                self.frame_temp_list[i].setLayout(self.layout_temp_list[i])
                self.frame_humid_list[i].setLayout(self.layout_humid_list[i])
                self.layout_channel_list[i].addWidget(self.frame_temp_list[i])
                self.layout_channel_list[i].addWidget(self.frame_humid_list[i])
                self.gb_list[i].setLayout(self.layout_channel_list[i])

            if self.config.getValue('Setting', 'disp_mode') == 0:
                display_left = 0
                display_right = 1
            elif self.config.getValue('Setting', 'disp_mode') == 1:
                display_left = 1
                display_right = 0
            else:
                display_left = 0
                display_right = 1

            self.layout_all = QGridLayout()
            self.layout_all.addWidget(self.gb_list[0], 0, display_left)
            self.layout_all.addWidget(self.gb_list[1], 1, display_left)
            self.layout_all.addWidget(self.gb_list[2], 2, display_left)
            self.layout_all.addWidget(self.gb_list[3], 3, display_left)

            self.layout_all.addWidget(self.gb_list[4], 0, display_right)
            self.layout_all.addWidget(self.gb_list[5], 1, display_right)
            self.layout_all.addWidget(self.gb_list[6], 2, display_right)
            self.layout_all.addWidget(self.gb_list[7], 3, display_right)

            self.layout_end = QVBoxLayout()
            self.layout_title = QHBoxLayout()
            self.layout_title.addWidget(self.id_label)
            self.layout_title.addStretch(1)
            self.layout_title.addWidget(self.wifi_icon)
            self.layout_title.addWidget(self.hw_icon)
            self.layout_title.addWidget(self.web_icon)
            self.layout_title.addWidget(self.delay_icon)
            # self.layout_title.addSpacing(50)
            self.layout_title.addSpacing(50)
            self.layout_title.addStretch(1)
            self.layout_title.addWidget(self.time_label)

            #self.layout_title.setContentsMargins(0, 0, 0, 50)
            #self.layout_all.setContentsMargins(0, 0, 0, 50)
            # self.layout_title.setSizeConstraint(QLayout.SetFixedSize)
            # self.layout_all.setSizeConstraint(QLayout.SetFixedSize)
            self.layout_end.addLayout(self.layout_title)
            #self.layout_end.addStretch(0)
            self.layout_end.addLayout(self.layout_all)
            #self.layout_end.addStretch(0)
            self.setLayout(self.layout_end)
            # widget = QWidget()
            # widget.setLayout(self.layout_end)
            # widget.resize(widget.sizeHint())

            self.setAutoFillBackground(True)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

    def mousePressEvent(self, event):
        try:
            self.close()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def refreshLayout(self, onList):
        try:
            for i in range(8):
                self.layout_all.removeWidget(self.gb_list[i])

            self.config = Config('config_th.ini', debug=False)
            self.disp_mode = self.config.getValue('Setting', 'disp_mode')

            rowIdx = 0
            colCount = 0

            if self.disp_mode == 0 :
                colIdx = 0
            else :
                colIdx = 1

            for i in range(8):
                if i in onList:
                    self.gb_list[i].update()
                    self.layout_all.addWidget(self.gb_list[i], rowIdx, colIdx)

                    if len(onList) == 1 and self.one_flag == 0:
                        self.layout_end.addSpacing(80)
                        self.one_flag = 1

                    rowIdx += 1
                    colCount += 1
                    rowIdx = rowIdx % 4

                    if colCount // 4 == 0 and self.disp_mode == 0:
                        colIdx = 0
                    elif colCount // 4 == 1 and self.disp_mode == 0:
                        colIdx = 1
                    elif colCount // 4 == 0 and self.disp_mode == 1:
                        colIdx = 1
                    else :
                        colIdx = 0
                else:
                    self.gb_list[i].hide()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def initStyle(self, onList=[]):
        try:
            self.refreshLayout(onList)

            for idx, item in enumerate(self.frame_temp_list):
                if idx in onList:
                    item.setStyleSheet("background-color: #ffffff;")
                    item.setFrameShape(QFrame.StyledPanel)

            for idx, item in enumerate(self.frame_humid_list):
                if idx in onList:
                    item.setStyleSheet("background-color: #ffffff;")
                    item.setFrameShape(QFrame.StyledPanel)

            for idx, item in enumerate(self.temp_label_list):
                if idx in onList:
                    fontSize = self.getFontSizeRate(len(onList))
                    self.label_fontSize = fontSize
                    item.setStyleSheet("color : black; font-size: %dpx;" % fontSize)
                    item.resize(item.sizeHint())

            for idx, item in enumerate(self.humid_label_list):
                if idx in onList:
                    item.setStyleSheet("color : black; font-size: %dpx;" % fontSize)
                    item.adjustSize()

            for idx, item in enumerate(self.temp_lcd_list):
                if idx in onList:
                    item.setSegmentStyle(QLCDNumber.Flat)
                    item.setStyleSheet("border-image: url(green.jpg);")

            for idx, item in enumerate(self.humid_lcd_list):
                if idx in onList:
                    item.setSegmentStyle(QLCDNumber.Flat)
                    item.setStyleSheet("border-image: url(blue.jpg);")

            for item in self.gb_list:
                item.setObjectName("ColoredGroupBox")
                fontSize = self.getFontSizeRate(len(onList))
                item.setStyleSheet("""
                    QGroupBox#ColoredGroupBox {border: 1px solid #9bd7d1; font-size: %dpx; font-weight: bold; margin-top: 2ex; color :#efeeee;}
                    QGroupBox::title{subcontrol-origin: margin; subcontrol-origin: margin; subcontrol-position: top center;}
                    """ % fontSize)

            for idx, item in enumerate(self.temp_icon_list):
                if idx in onList:
                    item.setFlat(True)
                    item.resize(item.sizeHint())
                    item.setStyleSheet("""
                                qproperty-icon: url("./icon_th/temperature.png"); /* empty image */
                                background-color:#ffffff;
                                """)
                    iconSize = self.getIconSizeRate(len(onList))
                    item.setIconSize(QSize(iconSize, iconSize))

            for idx, item in enumerate(self.humid_icon_list):
                if idx in onList:
                    item.setFlat(True)
                    item.resize(item.sizeHint())
                    item.setStyleSheet("""
                                qproperty-icon: url("./icon_th/humidity.png"); /* empty image */
                                background-color:#ffffff;
                                """)

                    iconSize = self.getIconSizeRate(len(onList))
                    item.setIconSize(QSize(iconSize, iconSize))

            self.wifi_icon.setStyleSheet("""
                                qproperty-icon: url("./icon_th/wifi_%d.png"); /* empty image */
                                qproperty-iconSize: 17px 17px; /* space for the background image */
                                """ % Main.wifi_status)
            self.hw_icon.setStyleSheet("""
                                qproperty-icon: url("./icon_th/hw_%d.png"); /* empty image */
                                qproperty-iconSize: 17px 17px; /* space for the background image */
                                """ % Main.hw_status)
            self.web_icon.setStyleSheet("""
                                qproperty-icon: url("./icon_th/web_%d.png"); /* empty image */
                                qproperty-iconSize: 17px 17px; /* space for the background image */
                                """ % Main.web_status)
            self.delay_icon.setStyleSheet("""
                                qproperty-icon: url("./icon_th/delaytime.png"); /* empty image */
                                qproperty-iconSize: 60px 25px; /* space for the background image */
                                """)
            
            #[240620_SeokJu.Yang_Add idLabelBackColor(if (QA_Alarm == 1) color changed red)
            # 여기다가 id_label 바뀌도록 추가?
            self.id_label.setStyleSheet(f"font-size: 14px; color : white; background-color: {Main.idLabelBackColor}; border : none")
            #]240620_SeokJu.Yang_Add idLabelBackColor(if (QA_Alarm == 1) color changed red)
            
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def getFontSizeRate(self, num):
        try:
            if num == 1:
                return 26
            elif num == 2:
                return 20
            elif num == 3:
                return 18
            elif num == 4:
                return 10
            else:
                return 10
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def getIconSizeRate(self, num):
        try:
            if num == 1:
                return 140
            elif num == 2:
                return 80
            elif num == 3:
                return 40
            elif num == 4:
                return 25
            else:
                return 25
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

class Setting(QWidget):
    id_signal = pyqtSignal()
    style_sheet = """
    QLabel{font : 11pt;
    color : black;}
    QTableWidget{color:black;}
    QRadioButton{ color :black; font:7pt; }
    QRadioButton:indicator{
        width : 14px;
        height : 14px;
        border-radius: 6px;
    }
    QRadioButton:indicator:checked{
        background-color: #f26627;
        border: 1px solid black;
    }
    QRadioButton:indicator:unchecked{
        background-color: #efeeee;
        border: 1px solid black;
    }
    QRadioButton{font:8pt;}
    QLineEdit{color : black;}
    """
    rs485 = RS485Event()
    
    def __init__(self):
        super().__init__()
        self.initUI()
        self.initSignal()
        self.initStyle()
        self.createTable()
        self.initEdit()

    def initUI(self):
        try:
            self.config = Config('config_th.ini', debug=False)
            self.keyboardWidget = KeyboardWidget()
            self.keyboardWidget.hide()
            self.title_label = QLabel("Setting")
            self.title_label.setFont((QtGui.QFont("Arial", 13, weight=80)))
            self.id_label = QLabel("ID : ")
            self.read_label = QLabel("Read : ")
            self.write_label = QLabel("Write : ")
            self.read_unit_label = QLabel("(sec)")
            self.write_unit_label = QLabel("(min)")
            self.pw_label = QLabel("Password : ")

            self.web_label = QLabel("Web service : ")
            self.board_label = QLabel("USB I/O Board : ")
            self.rpipin_label = QLabel("External Output : ")
            self.display_label = QLabel("Display : ")
            self.delay_label = QLabel("Alarm Delay : ")
            self.delaytime_label = QLabel("Use Delaytime : ")
            self.sn_label = QLabel("Serial Number : ")

            self.sensorpos_label = QLabel("Sensor : ")
            self.humidoffset_label = QLabel("Humid : ")

            self.id_edit = VKQLineEdit(name="id", mainWindowObj=self)
            self.id_edit.setAlignment(QtCore.Qt.AlignCenter)
            self.read_edit = VKQLineEdit(name="read", mainWindowObj=self)
            self.read_edit.setAlignment(QtCore.Qt.AlignCenter)
            self.write_edit = VKQLineEdit(name="write", mainWindowObj=self)
            self.write_edit.setAlignment(QtCore.Qt.AlignCenter)
            self.pw_edit = VKQLineEdit(name="pw", mainWindowObj=self)
            self.pw_edit.setAlignment(QtCore.Qt.AlignCenter)

            self.sensorpos_edit = VKQLineEdit(name="sensor", mainWindowObj=self)
            self.sensorpos_edit.setAlignment(QtCore.Qt.AlignCenter)

            self.humid_edit = VKQLineEdit(name="humid", mainWindowObj=self)
            self.humid_edit.setAlignment(QtCore.Qt.AlignCenter)

            self.delay_edit = VKQLineEdit(name="delay", mainWindowObj=self)
            self.delay_edit.setAlignment(QtCore.Qt.AlignCenter)
            
            self.sn_edit = VKQLineEdit(name="sn", mainWindowObj=self)
            self.sn_edit.setAlignment(QtCore.Qt.AlignCenter)
            self.change_serial = self.config.getValue('Setting', 'change_serial')
            self.sn_edit.setDisabled(self.change_serial)
            
            self.save_button = QPushButton('')
            self.save_button.setFlat(True)
            self.save_button.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            self.save_button.setStyleSheet("""
            background-color:#334455;
            qproperty-icon: url("./icon_th/save.png"); /* empty image */
            qproperty-iconSize: 37px 60px; /* space for the background image */
            background-color:#334455;
            """)

            self.init_button = QPushButton('')
            self.init_button.setFlat(True)
            self.init_button.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            self.init_button.setStyleSheet("""
            qproperty-icon: url("./icon_th/config.png"); /* empty image */
            qproperty-iconSize: 37px 60px; /* space for the background image */
            background-color:#112233;
            """)

            self.bright_button = QPushButton('')
            self.bright_button.setFlat(True)
            self.bright_button.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            self.bright_button.setStyleSheet("""
            qproperty-icon: url("./icon_th/brightness.png"); /* empty image */
            qproperty-iconSize: 37px 60px; /* space for the background image */
            background-color:#112233;
            """)

            self.ch_group_list = []
            self.on_radio_list = []
            self.off_radio_list = []
            self.layout_ch_list = []

            for i in range(8):
                group = QGroupBox("{}".format(i + 1))
                self.ch_group_list.append(group)

                on = QRadioButton("Enable")
                self.on_radio_list.append(on)

                off = QRadioButton("Disable")
                self.off_radio_list.append(off)

                layout = QHBoxLayout()
                self.layout_ch_list.append(layout)

                self.ch_group_list[i].setLayout(self.layout_ch_list[i])
                self.ch_group_list[i].setMaximumWidth(200)
                self.ch_group_list[i].setMaximumHeight(36)
                self.layout_ch_list[i].addWidget(on)
                self.layout_ch_list[i].addWidget(off)

            self.web_on_radio = QRadioButton("On")
            self.web_off_radio = QRadioButton("Off")
            self.web_service_group = QButtonGroup()
            self.web_service_group.addButton(self.web_on_radio)
            self.web_service_group.addButton(self.web_off_radio)

            self.board_on_radio = QRadioButton("On")
            self.board_off_radio = QRadioButton("Off")
            self.board_group = QButtonGroup()
            self.board_group.addButton(self.board_on_radio)
            self.board_group.addButton(self.board_off_radio)

            self.pin_on_radio = QRadioButton("On")
            self.pin_off_radio = QRadioButton("Off")
            self.pin_group = QButtonGroup()
            self.pin_group.addButton(self.pin_on_radio)
            self.pin_group.addButton(self.pin_off_radio)
            
            self.delaytime_on_radio = QRadioButton("On")
            self.delaytime_off_radio = QRadioButton("Off")
            self.delaytime_group = QButtonGroup()
            self.delaytime_group.addButton(self.delaytime_on_radio)
            self.delaytime_group.addButton(self.delaytime_off_radio)

            self.disp_radio_left = QCheckBox('left', self)
            self.disp_radio_right = QCheckBox('right', self)
            self.delay_check = QCheckBox('ON', self)
            
            self.layout_group_left = QVBoxLayout()
            self.layout_group_left.addWidget(self.ch_group_list[0])
            self.layout_group_left.addWidget(self.ch_group_list[1])
            self.layout_group_left.addWidget(self.ch_group_list[2])
            self.layout_group_left.addWidget(self.ch_group_list[3])

            self.layout_group_right = QVBoxLayout()
            self.layout_group_right.addWidget(self.ch_group_list[4])
            self.layout_group_right.addWidget(self.ch_group_list[5])
            self.layout_group_right.addWidget(self.ch_group_list[6])
            self.layout_group_right.addWidget(self.ch_group_list[7])
            
            self.edit_table = QTableWidget()
            self.edit_table.setFixedWidth(520)
            self.layout_id = QHBoxLayout()
            self.layout_read = QHBoxLayout()
            self.layout_write = QHBoxLayout()
            self.layout_pw = QHBoxLayout()
            self.layout_up = QHBoxLayout()
            self.layout_down = QHBoxLayout()
            self.layout_all = QVBoxLayout()

            self.layout_sensor = QHBoxLayout()
            self.layout_humid = QHBoxLayout()

            self.layout_id.addWidget(self.id_label)
            self.layout_id.addWidget(self.id_edit)
            self.layout_read.addWidget(self.read_label)
            self.layout_read.addWidget(self.read_edit)
            self.layout_read.addWidget(self.read_unit_label)
            self.layout_write.addWidget(self.write_label)
            self.layout_write.addWidget(self.write_edit)
            self.layout_write.addWidget(self.write_unit_label)

            self.layout_sensor.addWidget(self.sensorpos_label)
            self.layout_sensor.addWidget(self.sensorpos_edit)

            self.layout_humid.addWidget(self.humidoffset_label)
            self.layout_humid.addWidget(self.humid_edit)

            self.layout_pw.addWidget(self.pw_label)
            self.layout_pw.addWidget(self.pw_edit)

            self.layout_up_1 = QVBoxLayout()
            self.layout_up_1.addLayout(self.layout_id)
            self.layout_up_1.addLayout(self.layout_pw)

            self.layout_up_2 = QVBoxLayout()
            self.layout_up_2.addLayout(self.layout_read)
            self.layout_up_2.addLayout(self.layout_write)

            self.layout_up_3 = QVBoxLayout()
            self.layout_up_3.addLayout(self.layout_sensor)
            self.layout_up_3.addLayout(self.layout_humid)

            self.layout_up.addLayout(self.layout_up_1)
            self.layout_up.addSpacing(10)
            self.layout_up.addLayout(self.layout_up_2)

            self.layout_up.addLayout(self.layout_up_3)
            self.layout_up.addSpacing(25)

            self.layout_up.addWidget(self.save_button)
            self.layout_up.addSpacing(10)
            self.layout_up.addWidget(self.init_button)
            self.layout_up.addSpacing(10)
            self.layout_up.addWidget(self.bright_button)
            self.layout_up.addSpacing(10)

            self.layout_web = QHBoxLayout()
            self.layout_web.addWidget(self.web_label)
            self.layout_web.addStretch(4)
            self.layout_web.addWidget(self.web_on_radio)
            self.layout_web.addWidget(self.web_off_radio)
            self.layout_web.addStretch(1)

            self.layout_board = QHBoxLayout()
            self.layout_board.addWidget(self.board_label)
            self.layout_board.addStretch(4)
            self.layout_board.addWidget(self.board_on_radio)
            self.layout_board.addWidget(self.board_off_radio)
            self.layout_board.addStretch(1)

            self.layout_rpipin = QHBoxLayout()
            self.layout_rpipin.addWidget(self.rpipin_label)
            self.layout_rpipin.addStretch(4)
            self.layout_rpipin.addWidget(self.pin_on_radio)
            self.layout_rpipin.addWidget(self.pin_off_radio)
            self.layout_rpipin.addStretch(1)

            self.layout_disp = QHBoxLayout()
            self.layout_disp.addWidget(self.display_label)
            self.layout_disp.addStretch(7)
            self.layout_disp.addWidget(self.disp_radio_left)
            self.layout_disp.addStretch(1)
            self.layout_disp.addWidget(self.disp_radio_right)
            self.layout_disp.addStretch(1)
            
            self.layout_delay = QHBoxLayout()
            self.layout_delay.addWidget(self.delay_label)
            self.layout_delay.addWidget(self.delay_edit)
            self.layout_delay.addWidget(self.delay_check)

            self.layout_delaytime = QHBoxLayout()
            self.layout_delaytime.addWidget(self.delaytime_label)
            self.layout_delaytime.addStretch(4)
            self.layout_delaytime.addWidget(self.delaytime_on_radio)
            self.layout_delaytime.addWidget(self.delaytime_off_radio)
            self.layout_delaytime.addStretch(1)
            
            self.layout_sn = QHBoxLayout()
            self.layout_sn.addWidget(self.sn_label)
            self.layout_sn.addStretch(5)
            self.layout_sn.addWidget(self.sn_edit)
            self.layout_sn.addStretch(1)

            self.layout_down_right = QVBoxLayout()

            self.layout_down_right.addLayout(self.layout_web)
            self.layout_down_right.addLayout(self.layout_board)
            self.layout_down_right.addLayout(self.layout_rpipin)
            self.layout_down_right.addLayout(self.layout_disp)
            self.layout_down_right.addLayout(self.layout_delay)
            self.layout_down_right.addLayout(self.layout_delaytime)
            self.layout_down_right.addLayout(self.layout_sn)

            self.layout_down.addWidget(self.edit_table)
            self.layout_down.addLayout(self.layout_down_right)

            self.layout_all.addLayout(self.layout_up)
            self.layout_all.addLayout(self.layout_down)

            self.setLayout(self.layout_all)
            self.setStyleSheet(self.style_sheet)

            self.setAutoFillBackground(True)
            p = self.palette()
            p.setColor(self.backgroundRole(), QColor("#f1e6c1"))
            self.setPalette(p)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

    def initSignal(self):
        try:
            self.save_button.clicked.connect(self.saveButtonClicked)
            self.init_button.clicked.connect(self.initButtonClicked)
            self.bright_button.clicked.connect(self.brightButtonClicked)
            self.board_off_radio.clicked.connect(self.board_off_radioClicked)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def initStyle(self):
        try:
            for i in range(8):
                self.ch_group_list[i].setStyleSheet("""
                QGroupBox{
                font:8pt bold;
                border:1px solid #1c4e80;
                border-bottom-left-radius:5px;
                }
                QGroupBox:title{
                subcontrol-position:left;
                padding-left : 4px;
                left:-6px;
                top: -13px;
                }
                """)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def board_off_radioClicked(self):
        try:
            self.config = Config('config_th.ini', debug=False)
            self.reply = QMessageBox()
            self.reply.setIcon(QMessageBox.Question)
            self.reply.setWindowTitle('Board Off')
            self.reply.setText('Use not I/O Board control\nPlease check N2 On/Off')
            self.reply.setStandardButtons(QMessageBox.Yes|QMessageBox.No)
            replyY = self.reply.button(QMessageBox.Yes)
            replyY.setText('N2 Off')
            replyN = self.reply.button(QMessageBox.No)
            replyN.setText('N2 On')
            self.reply.exec_()
            if self.reply.clickedButton() == replyY:
                self.config.setValue("Setting","board_off_option",0)
                self.config.save()
                logger.debug("Board_off_option : check N2 Off")
                QMessageBox.information(self, "QMessageBox", "N2 Off!")
            elif self.reply.clickedButton() == replyN:
                self.config.setValue("Setting","board_off_option",1)
                self.config.save()
                logger.debug("Board_off_option : check N2 On")
                QMessageBox.information(self, "QMessageBox", "N2 On!")
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
    def editControl(self):
        try:
            cb = self.sender()
            self.disIdx_list = list(set(self.disIdx_list))
            if cb.isChecked():
                try:
                    self.disIdx_list.remove(cb.idx)
                except:
                    pass
            else:
                self.disIdx_list.append(cb.idx)

            self.disIdx_list = list(set(self.disIdx_list))

            for i in range(8):
                if i in self.disIdx_list:
                    self.offset_temp_edit_list[i].setEnabled(False)
                    self.offset_humid_edit_list[i].setEnabled(False)
                    self.temp_min_edit_list[i].setEnabled(False)
                    self.temp_max_edit_list[i].setEnabled(False)
                    self.humid_min_edit_list[i].setEnabled(False)
                    self.humid_max_edit_list[i].setEnabled(False)
                else:
                    self.offset_temp_edit_list[i].setEnabled(True)
                    self.offset_humid_edit_list[i].setEnabled(True)
                    self.temp_min_edit_list[i].setEnabled(True)
                    self.temp_max_edit_list[i].setEnabled(True)
                    self.humid_min_edit_list[i].setEnabled(True)
                    self.humid_max_edit_list[i].setEnabled(True)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
    
    def is_digit(self, str):
        try:
            tmp = float(str)
            return True
        except ValueError:
            return False
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

    def createTable(self):
        try:
            self.edit_table.setRowCount(10)
            self.edit_table.setColumnCount(8)
            self.edit_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
            self.edit_table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
            self.edit_table.verticalHeader().setVisible(False)
            self.edit_table.horizontalHeader().setVisible(False)

            # column header 세팅
            col_header = ["Offset", "Temperature", "Humidity"]
            idx = -1
            for item in col_header:
                idx += 2
                self.edit_table.setSpan(0, idx, 1, 2)
                content = QTableWidgetItem(item)
                content.setFont((QtGui.QFont("고딕", 11, weight=80)))
                content.setFlags(QtCore.Qt.ItemIsEnabled)
                content.setTextAlignment(Qt.AlignCenter)
                content.setForeground(QColor("#FFFFFF"))
                self.edit_table.setItem(0, idx, content)

            enable = QTableWidgetItem("Enable")
            enable.setFont((QtGui.QFont("고딕", 10, weight=60)))
            enable.setFlags(QtCore.Qt.ItemIsEnabled)
            enable.setTextAlignment(Qt.AlignCenter)
            self.edit_table.setItem(0, 7, enable)
            self.edit_table.setSpan(0, 7, 2, 1)

            col_header = ["Temp", "Humid", "Min", "Max", "Min", "Max"]
            for idx, item in enumerate(col_header):
                content = QTableWidgetItem(item)
                content.setFlags(QtCore.Qt.ItemIsEnabled)
                content.setTextAlignment(Qt.AlignCenter)
                self.edit_table.setItem(1, idx + 1, content)

            self.edit_table.setSpan(0, 0, 2, 1)
            self.edit_table.item(0, 1).setBackground(QColor("#7e909a"))
            self.edit_table.item(0, 3).setBackground(QColor("#4CAF50"))
            self.edit_table.item(0, 5).setBackground(QColor("#03A9F4"))

            # 채널 번호 세팅
            self.enable_chBox_list = []
            for i in range(8):
                content = QTableWidgetItem('{}'.format(i + 1))
                content.setFlags(QtCore.Qt.ItemIsEnabled)
                content.setTextAlignment(Qt.AlignCenter)
                content.setFont((QtGui.QFont("고딕", 12, weight=70)))
                self.edit_table.setItem(i + 2, 0, content)

                cb = QCheckBox("", self)
                cb.idx = i
                cb.stateChanged.connect(self.editControl)
                self.enable_chBox_list.append(cb)
                layout_cb = QHBoxLayout()
                layout_cb.setAlignment(Qt.AlignCenter)
                layout_cb.addWidget(self.enable_chBox_list[i])
                ch_widget = QWidget()
                ch_widget.setLayout(layout_cb)
                self.edit_table.setCellWidget(i + 2, 7, ch_widget)

            set_icon = QPushButton("")
            set_icon.setStyleSheet("""
            qproperty-icon: url("./icon_th/tools.png"); /* empty image */
            qproperty-iconSize: 16px 16px; /* space for the background image */
            background-color:#ffffff;
            """)
            set_icon.setEnabled(False)
            self.edit_table.setCellWidget(0, 0, set_icon)

            # 입력 시 가운데 정렬
            delegate = CenterDelegate()
            self.edit_table.setItemDelegate(delegate)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
    def brightButtonClicked(self):
        try:
            self.bright = BrightControl()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
    def saveButtonClicked(self):
        try:
            self.config = Config('config_th.ini', debug=False)
            
            box = QMessageBox()
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("Setting save")
            box.setWindowFlags(Qt.WindowStaysOnTopHint)
            box.setText("Are you sure want to save?")
            box.setStandardButtons(QMessageBox.No | QMessageBox.Yes)
            buttonN = box.button(QMessageBox.Yes)
            buttonN.setText("No")
            buttonY = box.button(QMessageBox.No)
            buttonY.setText("Yes")
            box.exec_()

            if box.clickedButton() == buttonY:
                self.empty_flag = 0
                self.not_decimal_flag = 0

                if self.board_on_radio.isChecked() and self.pin_on_radio.isChecked():
                    box = QMessageBox()
                    box.setIcon(QMessageBox.Critical)
                    box.setWindowTitle("Setting save")
                    box.setWindowFlags(Qt.FramelessWindowHint)
                    box.setText('"USB I/O Board" and "External Output" cannot be "on" at the same time\n please check 0 or 1')
                    box.setStandardButtons(QMessageBox.Ok)
                    box.exec_()
                    return

                if self.board_on_radio.isChecked():
                    try:
                        self.rs485.open()
                    except:
                        box = QMessageBox()
                        box.setIcon(QMessageBox.Critical)
                        box.setWindowTitle("Setting save")
                        box.setWindowFlags(Qt.FramelessWindowHint)
                        box.setText('USB I/O Board is not connected\n please check USB port')
                        box.setStandardButtons(QMessageBox.Ok)
                        box.exec_()
                        return

                self.empty_check_list = [self.id_edit, self.read_edit, self.sensorpos_edit, self.pw_edit, self.write_edit, self.humid_edit, self.delay_edit, self.sn_edit]
                for item in self.empty_check_list:
                    if item.text() == "":
                        self.empty_flag = 1
                        
                self.digit_check_list = [self.read_edit, self.write_edit, self.humid_edit, self.delay_edit]
                for item in self.digit_check_list:
                    if not self.is_digit(item.text().strip()):
                        self.not_decimal_flag = 1
                
                #[240621_SeokJu.Yang_before setting value save
                self.before_id_edit = self.config.getValue('Setting', 'id')
                self.before_sn_edit = self.config.getValue('Setting', 'serial_number')
                self.before_len_on_channel = self.config.getValue('Setting', 'len_on_channel')
                #]240621_SeokJu.Yang_before setting value save
                
                set_name_list = ['offset_temp', 'offset_humid', 'temp_min', 'temp_max', 'humid_min', 'humid_max', 'on', 'boot']
                self.len_on_channel = 0
                for i in range(8):
                    for idx, item in enumerate(set_name_list):
                        if idx == 0:
                            self.config.setValue(str(i + 1), item, self.offset_temp_edit_list[i].text().strip())
                            if not self.is_digit(self.offset_temp_edit_list[i].text().strip()):
                                self.not_decimal_flag = 1
                            if self.offset_temp_edit_list[i].text().strip() == "":
                                self.empty_flag = 1
                        elif idx == 1:
                            self.config.setValue(str(i + 1), item, self.offset_humid_edit_list[i].text().strip())
                            if not self.is_digit(self.offset_humid_edit_list[i].text().strip()):
                                self.not_decimal_flag = 1
                            if self.offset_humid_edit_list[i].text().strip() == "":
                                self.empty_flag = 1
                        elif idx == 2:
                            self.config.setValue(str(i + 1), item, self.temp_min_edit_list[i].text().strip())
                            if not self.is_digit(self.temp_min_edit_list[i].text().strip()):
                                self.not_decimal_flag = 1
                            if self.temp_min_edit_list[i].text().strip() == "":
                                self.empty_flag = 1
                        elif idx == 3:
                            self.config.setValue(str(i + 1), item, self.temp_max_edit_list[i].text().strip())
                            if not self.is_digit(self.temp_max_edit_list[i].text().strip()):
                                self.not_decimal_flag = 1
                            if self.temp_max_edit_list[i].text().strip() == "":
                                self.empty_flag = 1
                        elif idx == 4:
                            self.config.setValue(str(i + 1), item, self.humid_min_edit_list[i].text().strip())
                            if not self.is_digit(self.humid_min_edit_list[i].text().strip()):
                                self.not_decimal_flag = 1
                            if self.humid_min_edit_list[i].text().strip() == "":
                                self.empty_flag = 1
                        elif idx == 5:
                            self.config.setValue(str(i + 1), item, self.humid_max_edit_list[i].text().strip())
                            if not self.is_digit(self.humid_max_edit_list[i].text().strip()):
                                self.not_decimal_flag = 1
                            if self.humid_max_edit_list[i].text().strip() == "":
                                self.empty_flag = 1
                        elif idx == 6:
                            if self.enable_chBox_list[i].isChecked():
                                onOff = 1
                                self.len_on_channel += 1
                            else:
                                onOff = 0
                            self.config.setValue(str(i + 1), item, onOff)
                        elif idx == 7:
                            if self.web_on_radio.isChecked():
                                self.web_mode = 1
                            else:
                                self.web_mode = 0
                            self.config.setValue(str(i + 1), item, self.web_mode)   
                    if float(self.temp_min_edit_list[i].text().strip()) > float(self.temp_max_edit_list[i].text().strip()) or (float(self.humid_min_edit_list[i].text().strip()) + float(self.humid_edit.text().strip())) >= (float(self.humid_max_edit_list[i].text().strip()) - float(self.humid_edit.text().strip())):
                        box = QMessageBox()
                        box.setIcon(QMessageBox.Critical)
                        box.setWindowTitle("Setting save")
                        box.setWindowFlags(Qt.FramelessWindowHint)
                        box.setText("Minimum value exceed the Maximum value")
                        box.setStandardButtons(QMessageBox.Ok)
                        box.exec_()
                        return

                if self.empty_flag == 1:
                    box = QMessageBox()
                    box.setIcon(QMessageBox.Critical)
                    box.setWindowTitle("Setting save")
                    box.setWindowFlags(Qt.FramelessWindowHint)
                    box.setText("Empty value is exists")
                    box.setStandardButtons(QMessageBox.Ok)
                    box.exec_()
                    return
                    
                if self.not_decimal_flag == 1:
                    box = QMessageBox()
                    box.setIcon(QMessageBox.Critical)
                    box.setWindowTitle("Setting save")
                    box.setWindowFlags(Qt.FramelessWindowHint)
                    box.setText("Setting value is only decimal number")
                    box.setStandardButtons(QMessageBox.Ok)
                    box.exec_()
                    return

                if self.web_on_radio.isChecked():
                    self.web_mode = 1
                elif self.web_off_radio.isChecked():
                    self.web_mode = 0
                
                if self.board_on_radio.isChecked():
                    self.board_mode = 1
                elif self.board_off_radio.isChecked():
                    self.board_mode = 0
                                    
                if self.pin_on_radio.isChecked():
                    self.pin_mode = 1
                elif self.pin_off_radio.isChecked():
                    self.pin_mode = 0

                if self.disp_radio_left.isChecked() == True and self.disp_radio_right.isChecked() == False:
                    self.disp_mode = 0
                elif self.disp_radio_right.isChecked() == True and self.disp_radio_left.isChecked() == False:
                    self.disp_mode = 1
                else :
                    self.disp_mode = 0

                if self.delay_check.isChecked() == True :
                    self.delay_mode = 1
                else:
                    self.delay_mode = 0

                if self.delaytime_on_radio.isChecked():
                    self.delaytime_mode = 1
                elif self.delaytime_off_radio.isChecked():
                    self.delaytime_mode = 0

                self.config.setValue("Setting", "id", self.id_edit.text().strip())
                self.config.setValue("Setting", "read_interval", self.read_edit.text().strip())
                self.config.setValue("Setting", "weblist", self.sensorpos_edit.text().strip())
                self.config.setValue("Setting", "pw", self.pw_edit.text().strip())
                self.config.setValue("Setting", "write_interval", self.write_edit.text().strip())
                self.config.setValue("Setting", "humidoffset", self.humid_edit.text().strip())
                self.config.setValue("Setting", "boot", self.web_mode)
                self.config.setValue("Setting", "board_mode", self.board_mode)
                self.config.setValue("Setting", "pin_mode", self.pin_mode)
                self.config.setValue("Setting", "disp_mode", self.disp_mode)
                self.config.setValue("Setting", "delay_mode", self.delay_mode)
                self.config.setValue("Setting", "delaytime_mode", self.delaytime_mode)
                self.config.setValue("Setting", "delay_time", self.delay_edit.text().strip())
                self.config.setValue("Setting", "serial_number", self.sn_edit.text().strip())
                self.config.setValue("Setting", "len_on_channel", self.len_on_channel)
                
                #[QA request] setting save Validation ################################
                try:
                    self.kit_db = RECALL()
                    self.serial_number = self.config.getValue('Setting', 'serial_number')
                    self.ID = self.config.getValue('Setting', 'id')
                    self.kit_data = self.kit_db.Set_Config(self.serial_number)
                    self.current_plant = int(self.kit_data[0][2][1])
                    
                    # IP check
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    sock.connect(("pwnbit.kr",443))
                    sock.settimeout(None)
                
                    # add request
                    self.change_config_text = ""
                    self.change_config_flag = 0
                    # ID change
                    if self.kit_data != [] and self.before_id_edit != self.id_edit.text().strip():
                        self.change_config_text += str(f" [K{self.current_plant}]Change Shelf ID\n IP : {sock.getsockname()[0]}\n Location : {self.kit_data[0][4]}\n Setting id : {self.ID}\n Serial_Number : {self.kit_data[0][1]}\n")
                        self.change_config_text += str(f" Before : {self.before_id_edit} / After : {self.id_edit.text().strip()}\n")
                        self.change_config_flag = 1
                    # S/N change
                    if self.kit_data != [] and self.before_sn_edit != self.sn_edit.text().strip():
                        self.change_config_text += str(f"\n [K{self.current_plant}]Change Serial_Number\n IP : {sock.getsockname()[0]}\n Location : {self.kit_data[0][4]}\n Setting id : {self.ID}\n Serial_Number : {self.kit_data[0][1]}\n")
                        self.change_config_text += str(f" Before : {self.before_sn_edit} / After : {self.sn_edit.text().strip()}\n")
                        self.change_config_flag = 1                
                    # Channel_len change
                    if self.kit_data != [] and self.len_on_channel != self.before_len_on_channel:
                        self.change_config_text += str(f"\n [K{self.current_plant}]Change the number of sensors\n IP : {sock.getsockname()[0]}\n Location : {self.kit_data[0][4]}\n Setting id : {self.ID}\n Serial_Number : {self.kit_data[0][1]}\n")
                        self.change_config_text += str(f" Before : {self.before_len_on_channel} ea / After : {self.len_on_channel} ea")            
                        self.change_config_flag = 1
                    self.change_config_plant = None
                    if int(self.current_plant) == 3:
                        self.change_config_plant = 0
                    elif int(self.current_plant) == 4:
                        self.change_config_plant = 1
                    elif int(self.current_plant) == 5:
                        self.change_config_plant = 2
                
                    if self.change_config_flag == 1:
                        change_config_title = "WIP thermo-hygrometer : Information is changed"
                        smtp.Send_Mail(self.change_config_plant, change_config_title, self.change_config_text)
                        logger.debug("[Success]Change Config - QA send mail")
                except Exception as e:
                    print(f"[QA] setting save error : {e}")
                    logger.debug("[Fail]Change Config - QA send mail")
                ##########################################################################
                
                self.config.save()
                
                ###[Add board_off_option_N2 On/Off]
                self.board_off_option = self.config.getValue("Setting","board_off_option")
                if self.board_mode == 0 and self.board_off_option == 1:
                    try:
                        self.rs485.open()
                        for idx in range(8):
                            self.channel_check = self.config.getValue(str(idx + 1), "on")
                            try:
                                if self.channel_check == 1:
                                    self.rs485.write((idx, 1))
                                else:
                                    self.rs485.write((idx, 0))
                                logger.debug(f"Board option Success - channel : {idx + 1}, channel_on_check : {self.channel_check}, board_off_option : {self.board_off_option}")
                            except:
                                pass
                        self.rs485.close()
                    except Exception as e:
                        logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
                elif self.board_mode == 0 and self.board_off_option == 0:
                    try:
                        self.rs485.open()
                        for idx in range(8):
                            try:
                                self.rs485.write((idx, 0))
                                logger.debug(f"Board option Success - channel : {idx + 1}, board_off_option : {self.board_off_option}")
                            except:
                                pass
                        self.rs485.close()
                    except Exception as e:
                        logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
                box = QMessageBox()
                box.setIcon(QMessageBox.Information)
                box.setWindowTitle("Setting save")
                box.setWindowFlags(Qt.FramelessWindowHint)
                box.setText("Setting value is saved\n will be restarted...")
                box.setStandardButtons(QMessageBox.Ok)
                reply = box.exec_()

                self.id_signal.emit()

                # Config 값들의 수정사항들이 바로 적용 될 수 있도록 함.
                global signals
                signals.configChanged()

                time.sleep(1)
                os.execv(sys.executable, ['python3'] + sys.argv)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
    def initButtonClicked(self):
        try:
            self.initEdit()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
    def initEdit(self):
        try:
            self.config = Config('config_th.ini', debug=False)
            self.set_id = self.config.getValue('Setting', 'id')
            self.set_read_interval = self.config.getValue('Setting', 'read_interval')
            self.sensor = self.config.getValue('Setting', 'weblist')
            self.set_pw = self.config.getValue('Setting', 'pw')
            self.set_write_interval = self.config.getValue('Setting', 'write_interval')
            self.humidoff = str(self.config.getValue('Setting', 'humidoffset'))
            self.delay_time = self.config.getValue('Setting', 'delay_time')
            self.use_delaytime = self.config.getValue('Setting', 'delaytime_mode')
            self.serialnumber = self.config.getValue('Setting', 'serial_number')
            
            ###########seokju => if sensor config only number GUI show only Number###########
            if type(self.sensor) == int:
                self.sensor = (self.sensor,)
                self.sensor = str(self.sensor)
                self.sensor = self.sensor[1:-2]
            else:
                self.sensor = str(self.sensor)
                self.sensor = self.sensor[1:-1]
            #################################################################################

            self.web_mode = self.config.getValue('Setting', 'boot')
            self.board_mode = self.config.getValue('Setting', 'board_mode')
            self.pin_mode = self.config.getValue('Setting', 'pin_mode')
            self.disp_mode = self.config.getValue('Setting', 'disp_mode')
            self.delay_mode = self.config.getValue('Setting', 'delay_mode')
            self.delaytime_mode = self.config.getValue('Setting', 'delaytime_mode')
            self.set_offset_temp = []
            self.set_offset_humid = []
            self.set_temp_min = []
            self.set_temp_max = []
            self.set_humid_min = []
            self.set_humid_max = []
            self.set_on = []
            self.boot = 0

            # Config 파일에 써져있는 값들 get
            set_name_list = ['offset_temp', 'offset_humid', 'temp_min', 'temp_max', 'humid_min', 'humid_max', 'on', 'boot']
            for idx, item in enumerate(set_name_list):
                for i in range(8):
                    value = self.config.getValue('{}'.format(str(i + 1)), item)
                    if idx == 0:
                        self.set_offset_temp.append(value)
                    elif idx == 1:
                        self.set_offset_humid.append(value)
                    elif idx == 2:
                        self.set_temp_min.append(value)
                    elif idx == 3:
                        self.set_temp_max.append(value)
                    elif idx == 4:
                        self.set_humid_min.append(value)
                    elif idx == 5:
                        self.set_humid_max.append(value)
                    elif idx == 6:
                        self.set_on.append(value)
                    elif idx == 7:
                        self.boot = value
                    
            if self.web_mode == 1:
                print("webservice mode on ")
                Main.webservice_flag = 1
                # Monitor.monitor = PopMonitor()

            elif self.web_mode == 0:
                print("webservife mode off")
                Main.webservice_flag = 0
                # Monitor.monitor = PopMonitor()
                # controlGPIO(yellow_pin,1)
            
            self.id_edit.setText(str(self.set_id))
            self.read_edit.setText(str(self.set_read_interval))
            self.sensorpos_edit.setText(str(self.sensor))
            self.pw_edit.setText(str(self.set_pw))
            self.write_edit.setText(str(self.set_write_interval))
            self.humid_edit.setText(self.humidoff)
            self.delay_edit.setText(str(self.delay_time))
            self.sn_edit.setText(str(self.serialnumber))

            self.offset_temp_edit_list = []
            for i in range(8):
                myEdit = VKQLineEdit(name="offsetTemp", mainWindowObj=self, curText=str(self.set_offset_temp[i]))
                myEdit.setAlignment(QtCore.Qt.AlignCenter)
                self.offset_temp_edit_list.append(myEdit)
                self.edit_table.setCellWidget(i + 2, 1, myEdit)

            self.offset_humid_edit_list = []
            for i in range(8):
                myEdit = VKQLineEdit(name="offsetTemp", mainWindowObj=self, curText=str(self.set_offset_humid[i]))
                myEdit.setAlignment(QtCore.Qt.AlignCenter)
                self.offset_humid_edit_list.append(myEdit)
                self.edit_table.setCellWidget(i + 2, 2, myEdit)

            self.temp_min_edit_list = []
            for i in range(8):
                myEdit = VKQLineEdit(name="offsetTemp", mainWindowObj=self, curText=str(self.set_temp_min[i]))
                myEdit.setAlignment(QtCore.Qt.AlignCenter)
                self.temp_min_edit_list.append(myEdit)
                self.edit_table.setCellWidget(i + 2, 3, myEdit)

            self.temp_max_edit_list = []
            for i in range(8):
                myEdit = VKQLineEdit(name="offsetTemp", mainWindowObj=self, curText=str(self.set_temp_max[i]))
                myEdit.setAlignment(QtCore.Qt.AlignCenter)
                self.temp_max_edit_list.append(myEdit)
                self.edit_table.setCellWidget(i + 2, 4, myEdit)

            self.humid_min_edit_list = []
            for i in range(8):
                myEdit = VKQLineEdit(name="offsetTemp", mainWindowObj=self, curText=str(self.set_humid_min[i]))
                myEdit.setAlignment(QtCore.Qt.AlignCenter)
                self.humid_min_edit_list.append(myEdit)
                self.edit_table.setCellWidget(i + 2, 5, myEdit)

            self.humid_max_edit_list = []
            for i in range(8):
                myEdit = VKQLineEdit(name="offsetTemp", mainWindowObj=self, curText=str(self.set_humid_max[i]))
                myEdit.setAlignment(QtCore.Qt.AlignCenter)
                self.humid_max_edit_list.append(myEdit)
                self.edit_table.setCellWidget(i + 2, 6, myEdit)

            self.disIdx_list = []
            for i in range(8):
                value = self.set_on[i]
                if int(value) == 0:
                    self.disIdx_list.append(i)
                    self.enable_chBox_list[i].setChecked(False)
                else:
                    self.enable_chBox_list[i].setChecked(True)

            if self.web_mode == 1:
                self.web_on_radio.setChecked(True)
                self.web_off_radio.setChecked(False)
            else:
                self.web_off_radio.setChecked(True)
                self.web_on_radio.setChecked(False)
            
            if self.board_mode == 1 and self.pin_mode == 0:
                self.board_on_radio.setChecked(True)
                self.pin_off_radio.setChecked(True)
            elif self.board_mode == 0 and self.pin_mode == 1:
                self.board_off_radio.setChecked(True)
                self.pin_on_radio.setChecked(True)
            elif self.board_mode == 0 and self.pin_mode == 0:
                self.board_off_radio.setChecked(True)
                self.pin_off_radio.setChecked(True)
                
            if self.disp_mode == 0:
                self.disp_radio_left.setChecked(True)
                self.disp_radio_right.setChecked(False)
            elif self.disp_mode == 1:
                self.disp_radio_left.setChecked(False)
                self.disp_radio_right.setChecked(True)
        
            if self.delay_mode == 1:
                self.delay_check.setChecked(True)
            elif self.delay_mode == 0:
                self.delay_check.setChecked(False)
                
            if self.use_delaytime == 1:
                self.delaytime_on_radio.setChecked(True)
                self.delaytime_off_radio.setChecked(False)
            elif self.use_delaytime == 0:
                self.delaytime_off_radio.setChecked(True)
                self.delaytime_on_radio.setChecked(False)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
            
class BrightControl(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Popup)
        self.backlight = Backlight()
        self.initValue = int(self.backlight.brightness)
        self.initUI()
        self.show()

    
    def initUI(self):
        try:
            self.title_label = QLabel("Brightness Control")
            self.title_label.setFont((QtGui.QFont("고딕", 14, weight=70)))

            self.mySlider = QSlider(Qt.Horizontal, self)
            self.mySlider.setGeometry(30, 40, 200, 50)
            self.mySlider.setValue(self.initValue)
            self.mySlider.setRange(20, 100)

            self.status_label = QLabel("Current Brightness : ")
            self.status_label.setFont((QtGui.QFont("고딕", 12, weight=70)))
            self.status_label.setText(f"Current Brightness : {str(self.initValue)}")

            layout_all = QVBoxLayout()
            layout_all.addWidget(self.title_label)
            layout_all.addWidget(self.mySlider)
            layout_all.addWidget(self.status_label)

            self.setGeometry(250, 150, 320, 200)
            self.setLayout(layout_all)
            self.mySlider.valueChanged[int].connect(self.changeValue)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
    
    def changeValue(self, value):
        try:
            self.backlight.brightness = value
            self.status_label.setText(f"Current Brightness : {str(value)}")
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

class VKQLineEdit(QLineEdit):
    def __init__(self, parent=None, name=None, mainWindowObj=None, curText=""):
        super(VKQLineEdit, self).__init__(parent)
        self.setText(curText)
        self.name = name
        self.setFixedHeight(25)
        self.mainWindowObj = mainWindowObj
        self.setFocusPolicy(Qt.ClickFocus)

    
    def focusInEvent(self, e):
        try:
            self.mainWindowObj.keyboardWidget.currentTextBox = self
            self.mainWindowObj.keyboardWidget.showFullScreen()
            # self.setStyleSheet("border: 1px solid red;")
            super(VKQLineEdit, self).focusInEvent(e)
            focused_widget = QApplication.focusWidget()
            focused_widget.clearFocus()
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
    
    def mousePressEvent(self, e):
        try:
            self.setFocusPolicy(Qt.ClickFocus)
            super(VKQLineEdit, self).mousePressEvent(e)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
class KeyboardWidget(QWidget):
    def __init__(self, parent=None):
        super(KeyboardWidget, self).__init__(parent)
        # self.setWindowFlags(Qt.Popup)
        self.currentTextBox = None

        self.signalMapper = QSignalMapper(self)
        self.signalMapper.mapped[int].connect(self.buttonClicked)

        self.initUI()

    def initUI(self):
        try:
            layout = QGridLayout()

            p = self.palette()
            p.setColor(self.backgroundRole(), Qt.white)
            self.setPalette(p)
            self.setAutoFillBackground(True)
            self.text_box = QTextEdit()
            self.text_box.setFont(QFont('Arial', 12))
            self.text_box.setFixedHeight(50)
            self.text_box.setFixedWidth(750)
            layout.addWidget(self.text_box, 0, 0, 1, 14)

            names = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N',
                    'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', '+', '*',
                    '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '.', ',', '-', '_']
            """
            names = ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P', '7', '8', '9',
                    'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', '.', '4', '5', '6',
                    'Z', 'X', 'C', 'V', 'B', 'N', 'M', '-', ',', '0', '1', '2', '3']
            """

            positions = [(i + 1, j) for i in range(3) for j in range(14)]

            for position, name in zip(positions, names):
                if name == '':
                    continue
                button = QPushButton(name)
                button.setFont(QFont('Arial', 13))
                button.setFixedHeight(53)
                button.setFixedWidth(48)

                button.KEY_CHAR = ord(name)
                button.clicked.connect(self.signalMapper.map)
                self.signalMapper.setMapping(button, button.KEY_CHAR)
                layout.addWidget(button, *position)

            # Clear button
            clear_button = QPushButton('Clear')
            clear_button.setFixedHeight(25)
            clear_button.setFont(QFont('Arial', 12))
            clear_button.KEY_CHAR = Qt.Key_Clear
            layout.addWidget(clear_button, 5, 0, 1, 2)
            clear_button.clicked.connect(self.signalMapper.map)
            self.signalMapper.setMapping(clear_button, clear_button.KEY_CHAR)
            clear_button.setFixedHeight(40)

            # Back button
            back_button = QPushButton('Back')
            back_button.setFixedHeight(25)
            back_button.setFont(QFont('Arial', 12))
            back_button.KEY_CHAR = Qt.Key_Backspace
            layout.addWidget(back_button, 5, 2, 1, 2)
            back_button.clicked.connect(self.signalMapper.map)
            self.signalMapper.setMapping(back_button, back_button.KEY_CHAR)
            back_button.setFixedHeight(40)

            # Space button
            space_button = QPushButton('Space')
            space_button.setFixedHeight(25)
            space_button.setFont(QFont('Arial', 12))
            space_button.KEY_CHAR = Qt.Key_Space
            layout.addWidget(space_button, 5, 4, 1, 4)
            space_button.clicked.connect(self.signalMapper.map)
            self.signalMapper.setMapping(space_button, space_button.KEY_CHAR)
            space_button.setFixedHeight(40)

            # Done button
            done_button = QPushButton('Done')
            done_button.setFixedHeight(25)
            done_button.setFont(QFont('Arial', 12))
            done_button.KEY_CHAR = Qt.Key_Home
            layout.addWidget(done_button, 5, 8, 1, 3)
            done_button.clicked.connect(self.signalMapper.map)
            self.signalMapper.setMapping(done_button, done_button.KEY_CHAR)
            done_button.setFixedHeight(40)

            # Quit button
            quit_button = QPushButton('Quit')
            quit_button.setFixedHeight(25)
            quit_button.setFont(QFont('Arial', 12))
            layout.addWidget(quit_button, 5, 11, 1, 3)
            quit_button.clicked.connect(self.close)
            quit_button.setFixedHeight(40)

            self.setGeometry(10, 75, 400, 300)
            self.setLayout(layout)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
    def buttonClicked(self, char_ord):
        try:
            txt = self.text_box.toPlainText()

            if char_ord == Qt.Key_Backspace:
                txt = txt[:-1]
            elif char_ord == Qt.Key_Enter:
                txt += chr(10)
                self.hide()
            elif char_ord == Qt.Key_Home:
                self.currentTextBox.setText(txt)
                self.text_box.setText("")
                self.hide()
                return
            elif char_ord == Qt.Key_Clear:
                txt = ""
            elif char_ord == Qt.Key_Space:
                txt += ' '
            elif char_ord < 0x110000:
                txt += chr(char_ord)
            else:
                txt += ""

            self.text_box.setText(txt)
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")
            
class CenterDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        try:
            editor = QStyledItemDelegate.createEditor(self, parent, option, index)
            editor.setAlignment(Qt.AlignCenter)
            return editor
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}][{sys._getframe().f_code.co_name}][Exception] : {e}")

if __name__ == '__main__':
    os.environ["QT_IM_MODULE"] = "qtvirtualkeyboard"
    app = QApplication(sys.argv)
    ex = Main()
    ex.show()
    app.setFont(QFont("고딕"))
    app.setWindowIcon(QtGui.QIcon('./icon_th/logo.png'))
    sys.exit(app.exec_())

GPIO.cleanup()