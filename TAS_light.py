#!/usr/bin/env python3
import tkinter as tk #Biblioteca padrão para montar a interface gráfica
from tkinter import filedialog, ttk, messagebox 
import requests #Biblioteca para criar solicitações HTTP 
import pandastable as pdt
import pandas as pd
import os
import serial
import time #Biblioteca padrão para setar pausas e marcações temporais
import socket
import numpy as np
import threading
import logging
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("tas_gui.log"),
        logging.StreamHandler()
    ]
)

# Constants for device connections
OSC_IP = "143.107.228.100"  # Oscilloscope IP address
OSC_PORT = 4000             # Oscilloscope port
SERIAL_PORT = "COM6"        # Arduino serial port
BAUD_RATE = 9600            # Serial communication baud rate

import serial
import threading
import time
import logging
from tkinter import messagebox

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("tas_gui.log"),
        logging.StreamHandler()
    ]
)

class ArduinoController:
    """
    Controller class to manage Arduino connections and operations.
    """
    def __init__(self, gui, tab):
        self.gui = gui
        self.tab = tab
        self.serial_conn = None
        self.is_connected = False
        self.relay_states = {
            '10': '0',
            '23': '2',
            '45': '5',
            '67': '7',
            '89': '9',
            'ab': 'b',
            'cd': 'd',
            'ef': 'f',
            'gh': 'h'
        }
        self.serial_lock = threading.Lock()
        self.read_thread = None
        self.reading = False
        self.create_controls()

    def create_controls(self):
        """
        Create GUI controls for the Arduino tab.
        """
        # Status Label
        status_label = tk.Label(self.tab, text="Arduino Status:", bg='#BBBBBB')
        status_label.grid(row=0, column=0, padx=10, pady=10, sticky='w')

        # Status Indicator
        self.Arduino_Status = tk.Label(self.tab, bg='red', width=2)
        self.Arduino_Status.grid(row=0, column=1, padx=10, pady=10, sticky='w')

        # Initialize and Disconnect Buttons
        self.Arduino_Init = tk.Button(
            self.tab,
            bg='orange',
            fg='white',
            text="Initialize",
            command=self.initialize
        )
        self.Arduino_Init.grid(row=0, column=2, padx=10, pady=10)

        self.Arduino_Disconnect = tk.Button(
            self.tab,
            bg='red',
            fg='white',
            text="Disconnect",
            command=self.disconnect,
            state='disabled'
        )
        self.Arduino_Disconnect.grid(row=0, column=3, padx=10, pady=10)

        # Relay Buttons
        relay_info = [
            ('10', 'IR'),
            ('23', 'VIS'),
            ('45', '100 Ohm'),
            ('67', '1 kOhm'),
            ('89', '5 kOhm'),
            ('ab', '10 kOhm'),
            ('cd', '50 kOhm'),
            ('ef', '100 kOhm'),
            ('gh', '500 kOhm'),
        ]

        self.relay_buttons = {}
        for idx, (relay_id, label) in enumerate(relay_info):
            btn = tk.Button(
                self.tab,
                bg='grey',
                fg='white',
                text=label,
                state='disabled',
                command=lambda r=relay_id: self.toggle_relay(r)
            )
            row = 1 + idx // 5
            col = idx % 5
            btn.grid(row=row, column=col, padx=5, pady=5)
            self.relay_buttons[relay_id] = btn

        # Light Control Frame
        light_frame = tk.LabelFrame(self.tab, text="Light Control", bg='#BBBBBB')
        light_frame.grid(row=3, column=0, columnspan=5, padx=10, pady=10, sticky='ew')

        self.Arduino_light = tk.Entry(light_frame, width=10)
        self.Arduino_light.insert(0, "100")  # Default value
        self.Arduino_light.grid(row=0, column=0, padx=10, pady=10)

        self.TDS_lightButton = tk.Button(
            light_frame,
            bg='grey',
            fg='white',
            text="Set Light",
            command=self.set_light
        )
        self.TDS_lightButton.grid(row=0, column=1, padx=10, pady=10)

    def initialize(self):
        """
        Initialize the Arduino by establishing a serial connection.
        """
        SERIAL_PORT = "/dev/ttyACM0"  # Update as per your system
        BAUD_RATE = 9600  # Update if different

        try:
            self.serial_conn = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)  # Wait for Arduino to reset
            self.reset_relays()
            self.update_status_indicator('green')
            self.Arduino_Disconnect.config(state='normal')
            self.Arduino_Init.config(state='disabled')
            messagebox.showinfo("Arduino", "Arduino initialized successfully.")
            logging.info("Arduino initialized successfully.")

            # Start the serial reading thread
            self.reading = True
            self.read_thread = threading.Thread(target=self.read_serial, daemon=True)
            self.read_thread.start()
        except serial.SerialException as e:
            messagebox.showerror("Arduino Error", f"Failed to initialize Arduino: {e}")
            logging.error(f"Failed to initialize Arduino: {e}")
            self.update_status_indicator('red')
        except Exception as e:
            messagebox.showerror("Arduino Error", f"An unexpected error occurred: {e}")
            logging.error(f"Unexpected error during initialization: {e}")
            self.update_status_indicator('red')

    def disconnect(self):
        """
        Disconnect the Arduino by closing the serial connection.
        """
        try:
            if self.serial_conn and self.serial_conn.is_open:
                self.reading = False
                if self.read_thread and self.read_thread.is_alive():
                    self.read_thread.join(timeout=1)
                self.serial_conn.close()
                self.update_status_indicator('red')
                self.Arduino_Disconnect.config(state='disabled')
                self.Arduino_Init.config(state='normal')
                self.disable_relay_buttons()
                messagebox.showinfo("Arduino", "Arduino disconnected successfully.")
                logging.info("Arduino disconnected successfully.")
        except Exception as e:
            messagebox.showerror("Arduino Error", f"Failed to disconnect Arduino: {e}")
            logging.error(f"Failed to disconnect Arduino: {e}")

    def send_command(self, cmd):
        """
        Send a command to the Arduino via serial communication.
        """
        if self.serial_conn and self.serial_conn.is_open:
            try:
                with self.serial_lock:
                    command_str = f"{cmd} \r"  # Ensure carriage return
                    self.serial_conn.write(command_str.encode())
                    logging.info(f"Sent to Arduino: {command_str.strip()}")
            except serial.SerialException as e:
                messagebox.showerror("Arduino Error", f"Failed to send command: {e}")
                logging.error(f"Failed to send command to Arduino: {e}")
            except Exception as e:
                messagebox.showerror("Arduino Error", f"An unexpected error occurred: {e}")
                logging.error(f"Unexpected error when sending command: {e}")
        else:
            messagebox.showerror("Arduino Error", "Arduino is not connected.")
            logging.warning("Attempted to send command while Arduino is not connected.")

    def read_serial(self):
        """
        Continuously read from the serial port and handle incoming data.
        """
        while self.reading and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting:
                    response = self.serial_conn.readline().decode().strip()
                    if response:
                        logging.info(f"Received from Arduino: {response}")
                        # Optionally, update GUI elements based on response
            except serial.SerialException as e:
                logging.error(f"Serial exception: {e}")
                break
            except Exception as e:
                logging.error(f"Unexpected error while reading serial: {e}")
                break

    def update_status_indicator(self, color):
        """
        Update the Arduino status indicator color.
        """
        self.Arduino_Status.config(bg=color)
        self.is_connected = (color == 'green')
        state = 'normal' if self.is_connected else 'disabled'
        for btn in self.relay_buttons.values():
            btn.config(state=state)

    def reset_relays(self):
        """
        Reset all relays to their default states.
        """
        default_states = ['0', '2', '5', '7', '9', 'b', 'd', 'f', 'h']
        for relay_id, state in zip(self.relay_buttons.keys(), default_states):
            self.send_command(state)
            time.sleep(0.5)  # Small delay between commands
            self.relay_states[relay_id] = state
            self.update_relay_button(relay_id)

    def toggle_relay(self, relay_id):
        """
        Toggle the state of a relay when its button is pressed.
        """
        current_state = self.relay_states.get(relay_id, '0')
        new_state = self.get_new_state(relay_id, current_state)
        self.send_command(new_state)
        self.relay_states[relay_id] = new_state
        self.update_relay_button(relay_id)

    def get_new_state(self, relay_id, current_state):
        """
        Determine the new state of a relay based on its current state.
        """
        toggle_map = {
            '10': {'0': '1', '1': '0'},
            '23': {'2': '3', '3': '2'},
            '45': {'4': '5', '5': '4'},
            '67': {'6': '7', '7': '6'},
            '89': {'8': '9', '9': '8'},
            'ab': {'a': 'b', 'b': 'a'},
            'cd': {'c': 'd', 'd': 'c'},
            'ef': {'e': 'f', 'f': 'e'},
            'gh': {'g': 'h', 'h': 'g'},
        }
        return toggle_map.get(relay_id, {}).get(current_state, current_state)

    def update_relay_button(self, relay_id):
        """
        Update the color of the relay button based on its state.
        """
        state = self.relay_states.get(relay_id, '0')
        color = 'green' if state in ['0', '2', '4', '6', '8', 'a', 'c', 'e', 'g'] else 'red'
        self.relay_buttons[relay_id].config(bg=color)

    def disable_relay_buttons(self):
        """
        Disable all relay buttons and reset their color to grey.
        """
        for btn in self.relay_buttons.values():
            btn.config(bg='grey', state='disabled')

    def set_light(self):
        """
        Set the light intensity based on the user's input.
        Runs in a separate thread to prevent blocking the GUI.
        """
        thread = threading.Thread(target=self._set_light_thread, daemon=True)
        thread.start()

    def _set_light_thread(self):
        light = self.Arduino_light.get()
        try:
            light_value = float(light)
            if not (0 <= light_value <= 100):
                raise ValueError("Light value must be between 0 and 100.")
            light_stage = int(light_value / 100 * 4095)
            self.send_command(f"i {light_stage}")
            logging.info(f"Light set to stage: {light_stage}")
        except ValueError as ve:
            messagebox.showerror("Invalid Input", f"Please enter a valid number for light power (0-100): {ve}")
            logging.warning(f"Invalid light power input: {ve}")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")
            logging.error(f"Unexpected error in set_light: {e}")

    """
    Controller class to manage Arduino connections and operations.
    """
    def __init__(self, gui, tab):
        self.gui = gui
        self.tab = tab
        self.serial_conn = None
        self.is_connected = False
        self.relay_states = {
            '10': '0',
            '23': '2',
            '45': '5',
            '67': '7',
            '89': '9',
            'ab': 'b',
            'cd': 'd',
            'ef': 'f',
            'gh': 'h'
        }
        self.serial_lock = threading.Lock()  # Correct attribute name with underscore
        self.read_thread = None
        self.reading = False
        self.create_controls()

    def create_controls(self):
        """
        Create GUI controls for the Arduino tab.
        """
        # Status Label
        status_label = tk.Label(self.tab, text="Arduino Status:", bg='#BBBBBB')
        status_label.grid(row=0, column=0, padx=10, pady=10, sticky='w')

        # Status Indicator
        self.Arduino_Status = tk.Label(self.tab, bg='red', width=2)
        self.Arduino_Status.grid(row=0, column=1, padx=10, pady=10, sticky='w')

        # Initialize and Disconnect Buttons
        self.Arduino_Init = tk.Button(
            self.tab,
            bg='orange',
            fg='white',
            text="Initialize",
            command=self.initialize
        )
        self.Arduino_Init.grid(row=0, column=2, padx=10, pady=10)

        self.Arduino_Disconnect = tk.Button(
            self.tab,
            bg='red',
            fg='white',
            text="Disconnect",
            command=self.disconnect,
            state='disabled'
        )
        self.Arduino_Disconnect.grid(row=0, column=3, padx=10, pady=10)

        # Relay Buttons
        relay_info = [
            ('10', 'IR'),
            ('23', 'VIS'),
            ('45', '100 Ohm'),
            ('67', '1 kOhm'),
            ('89', '5 kOhm'),
            ('ab', '10 kOhm'),
            ('cd', '50 kOhm'),
            ('ef', '100 kOhm'),
            ('gh', '500 kOhm'),
        ]

        self.relay_buttons = {}
        for idx, (relay_id, label) in enumerate(relay_info):
            btn = tk.Button(
                self.tab,
                bg='grey',
                fg='white',
                text=label,
                state='disabled',
                command=lambda r=relay_id: self.toggle_relay(r)
            )
            row = 1 + idx // 5
            col = idx % 5
            btn.grid(row=row, column=col, padx=5, pady=5)
            self.relay_buttons[relay_id] = btn

        # Light Control Frame
        light_frame = tk.LabelFrame(self.tab, text="Light Control", bg='#BBBBBB')
        light_frame.grid(row=3, column=0, columnspan=5, padx=10, pady=10, sticky='ew')

        self.Arduino_light = tk.Entry(light_frame, width=10)
        self.Arduino_light.insert(0, "100")  # Default value
        self.Arduino_light.grid(row=0, column=0, padx=10, pady=10)

        self.TDS_lightButton = tk.Button(
            light_frame,
            bg='grey',
            fg='white',
            text="Set Light",
            command=self.set_light
        )
        self.TDS_lightButton.grid(row=0, column=1, padx=10, pady=10)

    def initialize(self):
        """
        Initialize the Arduino by establishing a serial connection.
        """
        try:
            self.serial_conn = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)  # Wait for Arduino to reset
            self.reset_relays()
            self.update_status_indicator('green')
            self.Arduino_Disconnect.config(state='normal')
            self.Arduino_Init.config(state='disabled')
            messagebox.showinfo("Arduino", "Arduino initialized successfully.")
            logging.info("Arduino initialized successfully.")

            # Start the serial reading thread
            self.reading = True
            self.read_thread = threading.Thread(target=self.read_serial, daemon=True)
            self.read_thread.start()
        except Exception as e:
            messagebox.showerror("Arduino Error", f"Failed to initialize Arduino: {e}")
            logging.error(f"Failed to initialize Arduino: {e}")
            self.update_status_indicator('red')
    
    def read_serial(self):
        """
        Continuously read from the serial port and handle incoming data.
        """
        while self.reading and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting:
                    response = self.serial_conn.readline().decode().strip()
                    if response:
                        logging.info(f"Received from Arduino: {response}")
                        # Optional: Process the response or update the GUI accordingly
            except Exception as e:
                logging.error(f"Error reading from Arduino: {e}")
                break

    def disconnect(self):
        """
        Disconnect the Arduino by closing the serial connection.
        """
        try:
            if self.serial_conn and self.serial_conn.is_open:
                self.reading = False
                if self.read_thread and self.read_thread.is_alive():
                    self.read_thread.join(timeout=1)
                self.serial_conn.close()
                self.update_status_indicator('red')
                self.Arduino_Disconnect.config(state='disabled')
                self.Arduino_Init.config(state='normal')
                self.disable_relay_buttons()
                messagebox.showinfo("Arduino", "Arduino disconnected successfully.")
                logging.info("Arduino disconnected successfully.")
        except Exception as e:
            messagebox.showerror("Arduino Error", f"Failed to disconnect Arduino: {e}")
            logging.error(f"Failed to disconnect Arduino: {e}")

    def update_status_indicator(self, color):
        """
        Update the Arduino status indicator color.
        """
        self.Arduino_Status.config(bg=color)
        self.is_connected = (color == 'green')
        state = 'normal' if self.is_connected else 'disabled'
        for btn in self.relay_buttons.values():
            btn.config(state=state)

    def reset_relays(self):
        """
        Reset all relays to their default states.
        """
        default_states = ['0', '2', '5', '7', '9', 'b', 'd', 'f', 'h']
        for relay_id, state in zip(self.relay_buttons.keys(), default_states):
            self.send_command(state)
            time.sleep(0.5)
            self.relay_states[relay_id] = state
            self.update_relay_button(relay_id)

    def toggle_relay(self, relay_id):
        """
        Toggle the state of a relay when its button is pressed.
        """
        current_state = self.relay_states.get(relay_id, '0')
        new_state = self.get_new_state(relay_id, current_state)
        self.send_command(new_state)
        self.relay_states[relay_id] = new_state
        self.update_relay_button(relay_id)

    def get_new_state(self, relay_id, current_state):
        """
        Determine the new state of a relay based on its current state.
        """
        toggle_map = {
            '10': {'0': '1', '1': '0'},
            '23': {'2': '3', '3': '2'},
            '45': {'4': '5', '5': '4'},
            '67': {'6': '7', '7': '6'},
            '89': {'8': '9', '9': '8'},
            'ab': {'a': 'b', 'b': 'a'},
            'cd': {'c': 'd', 'd': 'c'},
            'ef': {'e': 'f', 'f': 'e'},
            'gh': {'g': 'h', 'h': 'g'},
        }
        return toggle_map.get(relay_id, {}).get(current_state, current_state)

    def send_command(self, cmd):
        if self.serial_conn and self.serial_conn.is_open:
            try:
                with self.serial_lock:  # Ensure using 'serial_lock'
                    self.serial_conn.write((cmd + '\n').encode())
                    logging.info(f"Sent to Arduino: {cmd}")
            except Exception as e:
                messagebox.showerror("Arduino Error", f"Failed to send command: {e}")
                logging.error(f"Failed to send command to Arduino: {e}")
        else:
            messagebox.showerror("Arduino Error", "Arduino is not connected.")
            logging.warning("Attempted to send command while Arduino is not connected.")

    def update_relay_button(self, relay_id):
        """
        Update the color of the relay button based on its state.
        """
        state = self.relay_states.get(relay_id, '0')
        color = 'green' if state in ['0', '2', '4', '6', '8', 'a', 'c', 'e', 'g'] else 'red'
        self.relay_buttons[relay_id].config(bg=color)

    def disable_relay_buttons(self):
        """
        Disable all relay buttons and reset their color to grey.
        """
        for btn in self.relay_buttons.values():
            btn.config(bg='grey', state='disabled')

    def set_light(self):
        """
        Set the light intensity based on the user's input.
        Runs in a separate thread to prevent blocking the GUI.
        """
        thread = threading.Thread(target=self._set_light_thread)
        thread.start()

    def _set_light_thread(self):
        light = self.Arduino_light.get()
        try:
            light_value = float(light)
            if not (0 <= light_value <= 100):
                raise ValueError("Light value must be between 0 and 100.")
            light_stage = int(light_value / 100 * 4095)
            self.send_command(f"i {light_stage}")
            logging.info(f"Light set to stage: {light_stage}")
        except ValueError as ve:
            messagebox.showerror("Invalid Input", f"Please enter a valid number for light power (0-100): {ve}")
            logging.warning(f"Invalid light power input: {ve}")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")
            logging.error(f"Unexpected error in set_light: {e}")

class OscilloscopeController:
    """
    Controller class to manage oscilloscope connections and operations.
    """
    def __init__(self):
        pass  # Initialize if needed

    def send_command(self, command):
        """
        Send a SCPI command to the oscilloscope via TCP/IP.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((OSC_IP, OSC_PORT))
                s.sendall((command + '\n').encode())
                logging.info(f"Sent to Oscilloscope: {command}")
        except Exception as e:
            messagebox.showerror("Oscilloscope Error", f"Failed to send command: {e}")
            logging.error(f"Failed to send command to oscilloscope: {e}")

    def acquire_waveform(self, channel):
        """
        Acquire waveform data from the oscilloscope for the specified channel.
        """
        try:
            url = f"http://{OSC_IP}/getwfm.isf"
            params = {
                "command": f"select:{channel} on",
                "command": "save:waveform:fileformat internal",
                "wfmsend": "Get"
            }
            response = requests.get(url, params=params)
            response.raise_for_status()
            logging.info(f"Waveform data acquired for {channel}")
            return response.content
        except Exception as e:
            messagebox.showerror("Oscilloscope Error", f"Failed to acquire waveform: {e}")
            logging.error(f"Failed to acquire waveform: {e}")
            return None

    def convert_bin_to_dat(self, bin_data):
        """
        Convert binary waveform data to a .dat format for saving and analysis.
        """
        try:
            data = np.frombuffer(bin_data, dtype=np.float32)
            logging.info("Binary data converted to numerical format.")
            return data
        except Exception as e:
            messagebox.showerror("Data Conversion Error", f"Failed to convert data: {e}")
            logging.error(f"Failed to convert binary to dat: {e}")
            return None

    def run_measurement_cycle(self, run_id, dirpath):
        """
        Run a measurement cycle: acquire waveforms and save data.
        """
        try:
            self.send_command("ACQUIRE:STATE RUN")
            logging.info("Oscilloscope acquisition started.")
            time.sleep(5)  # Wait for data collection
            self.send_command("ACQUIRE:STATE STOP")
            logging.info("Oscilloscope acquisition stopped.")

            # Acquire waveforms from channels 1 and 2
            ch1_data = self.acquire_waveform("CH1")
            ch2_data = self.acquire_waveform("CH2")

            if ch1_data and ch2_data:
                el = self.convert_bin_to_dat(ch1_data)
                op = self.convert_bin_to_dat(ch2_data)
                if el is not None and op is not None:
                    self.save_waveform_data(run_id, el, op, dirpath)
                    return True
            return False
        except Exception as e:
            messagebox.showerror("Measurement Cycle Error", f"Measurement cycle failed: {e}")
            logging.error(f"Measurement cycle failed: {e}")
            return False

    def save_waveform_data(self, run_id, el, op, dirpath):
        """
        Save waveform data to .dat files for both channels.
        """
        try:
            filepath_el = os.path.join(dirpath, f"{run_id}_el_av.dat")
            filepath_op = os.path.join(dirpath, f"{run_id}_op_av.dat")
            np.savetxt(filepath_el, np.column_stack((np.arange(len(el)), el)), fmt='%.6e')
            np.savetxt(filepath_op, np.column_stack((np.arange(len(op)), op)), fmt='%.6e')
            logging.info(f"Waveform data saved for {run_id}")
        except Exception as e:
            messagebox.showerror("Data Saving Error", f"Failed to save data: {e}")
            logging.error(f"Failed to save waveform data: {e}")

class TAS_GUI:
    """
    Main GUI class for the application.
    """
    def __init__(self, root):
        self.root = root
        self.root.title("TAS GUI v2.0") #Cria título para janela da interface
        self.root.geometry("1200x800")  #Increased size for better layout
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing) #Bind the close event to a cleanup function

        # Initial settings
        self.dirpath = "/home/tas/001_TAS/000_TEST"
        self.currentRun = ""
        self.LastRun = ""
        self.runLine = 0
        self.measurement_thread = None
        self.stop_measurement = threading.Event()
        self.df = pd.DataFrame()

        self.osc_controller = OscilloscopeController()
        self.create_path_selection()
        self.create_graphics()
        self.create_tabs()
        self.create_measure_tab()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        """
        Handle the application closing event.
        """
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            if self.arduino.is_connected:
                self.arduino.disconnect()
            self.root.destroy()

    def create_path_selection(self):
        """
        Create controls for selecting the data directory path.
        """
        def set_path():
            dirpath_new = filedialog.askdirectory(initialdir=self.dirpath)
            if dirpath_new:
                self.dirpath = dirpath_new
                self.text_path.config(text=self.dirpath)
                os.makedirs(self.dirpath, exist_ok=True)
                logging.info(f"Selected Path: {self.dirpath}")

        frameP = tk.Frame(self.root, bg='#AAAAAA')
        frameP.pack(pady=10, fill='x')

        button_getPath = tk.Button(frameP, text="Select Path", command=set_path, height=1, width=15)
        button_getPath.pack(side='left', padx=10)

        self.text_path = tk.Label(frameP, text=self.dirpath, bg='#AAAAAA', anchor='w')
        self.text_path.pack(side='left', fill='x', expand=True, padx=10)

    def create_graphics(self):
        """
        Create plotting areas for displaying measurement data.
        """
        frameG = tk.Frame(self.root, bg='#BBBBBB')
        frameG.pack(pady=10, fill='both', expand=True)

        # Initialize Figures
        self.fig_top = Figure(figsize=(5, 4), dpi=100)
        self.fig_mid = Figure(figsize=(5, 4), dpi=100)

        # Channel 1 Plot
        self.ax_top = self.fig_top.add_subplot(111)
        self.ax_top.set_title("Channel 1 - EL")
        self.ax_top.set_xlabel("Time")
        self.ax_top.set_ylabel("EL")
        self.line_top, = self.ax_top.plot([], [], label='EL', color='blue')
        self.ax_top.legend()

        self.canvasTop = FigureCanvasTkAgg(self.fig_top, master=frameG)
        self.canvasTop.draw()
        self.canvasTop.get_tk_widget().pack(side='left', fill='both', expand=True)

        toolbarTop = NavigationToolbar2Tk(self.canvasTop, frameG)
        toolbarTop.update()
        self.canvasTop.get_tk_widget().pack(side='left', fill='both', expand=True)

        # Channel 2 Plot
        self.ax_mid = self.fig_mid.add_subplot(111)
        self.ax_mid.set_title("Channel 2 - OP")
        self.ax_mid.set_xlabel("Time")
        self.ax_mid.set_ylabel("OP")
        self.line_mid, = self.ax_mid.plot([], [], label='OP', color='green')
        self.ax_mid.legend()

        self.canvasMid = FigureCanvasTkAgg(self.fig_mid, master=frameG)
        self.canvasMid.draw()
        self.canvasMid.get_tk_widget().pack(side='left', fill='both', expand=True)

        toolbarMid = NavigationToolbar2Tk(self.canvasMid, frameG)
        toolbarMid.update()
        self.canvasMid.get_tk_widget().pack(side='left', fill='both', expand=True)

    def create_tabs(self):
        """
        Create tabs in the GUI for different control panels.
        """
        self.tabControl = ttk.Notebook(self.root)
        self.tabControl.pack(expand=1, fill='both')

        # Arduino Control Tab
        self.tab_ARDUINO = tk.Frame(self.tabControl, bg='#BBBBBB')
        self.tabControl.add(self.tab_ARDUINO, text="Arduino")
        self.arduino = ArduinoController(self, self.tab_ARDUINO)

        # TDS Control Tab
        self.tab_TDS = tk.Frame(self.tabControl, bg='#BBBBBB')
        self.tabControl.add(self.tab_TDS, text="TDS")
        self.create_tds_controls()

    def create_tds_controls(self):
        """
        Create controls for the TDS (Time Domain Spectroscopy) tab.
        """
        def set_time_scale():
            time_scale = TDS_timeTxt.get()
            self.osc_controller.send_command(f"HOR:SCALE {time_scale}")
            logging.info(f"Time scale set to {time_scale}")

        def set_load_resistance(resistance):
            # Placeholder for actual implementation
            self.osc_controller.send_command(f"LOAD:RES {resistance}")
            logging.info(f"Load resistance set to {resistance} Ohm")

        def download_channel(channel):
            filepath = filedialog.asksaveasfilename(defaultextension=".dat",
                                                    filetypes=[("Data Files", "*.dat"), ("All Files", "*.*")])
            if not filepath:
                return
            bin_data = self.osc_controller.acquire_waveform(channel)
            if bin_data:
                dat_data = self.osc_controller.convert_bin_to_dat(bin_data)
                if dat_data is not None:
                    np.savetxt(filepath, np.column_stack((np.arange(len(dat_data)), dat_data)), fmt='%.6e')
                    messagebox.showinfo("Download Complete", f"Channel {channel} data saved to {filepath}")
                    logging.info(f"Channel {channel} data saved to {filepath}")
            else:
                messagebox.showerror("Download Error", f"Failed to download data for Channel {channel}.")
                logging.error(f"Failed to download data for Channel {channel}.")

        # RUN and STOP Buttons
        TDS_run = tk.Button(
            self.tab_TDS,
            bg='grey',
            fg='white',
            text="RUN",
            command=lambda: self.osc_controller.send_command("ACQUIRE:STATE RUN")
        )
        TDS_run.grid(row=0, column=0, padx=10, pady=10)

        TDS_stop = tk.Button(
            self.tab_TDS,
            bg='grey',
            fg='white',
            text="STOP",
            command=lambda: self.osc_controller.send_command("ACQUIRE:STATE STOP")
        )
        TDS_stop.grid(row=0, column=1, padx=10, pady=10)

        # Impedance Buttons
        TDS_fif = tk.Button(
            self.tab_TDS,
            bg='grey',
            fg='white',
            text="FIF",
            command=lambda: set_load_resistance(0)
        )
        TDS_fif.grid(row=0, column=4, padx=10, pady=10)

        TDS_meg = tk.Button(
            self.tab_TDS,
            bg='grey',
            fg='white',
            text="MEG",
            command=lambda: set_load_resistance(5)
        )
        TDS_meg.grid(row=0, column=5, padx=10, pady=10)

        # Download Buttons for Channels 1 and 2
        TDS_dlCH1 = tk.Button(
            self.tab_TDS,
            bg='grey',
            fg='white',
            text="Download CH1",
            command=lambda: download_channel("CH1")
        )
        TDS_dlCH1.grid(row=0, column=2, padx=10, pady=10)

        TDS_dlCH2 = tk.Button(
            self.tab_TDS,
            bg='grey',
            fg='white',
            text="Download CH2",
            command=lambda: download_channel("CH2")
        )
        TDS_dlCH2.grid(row=0, column=3, padx=10, pady=10)

        # Time Scale Entry and Button
        TDS_timeTxt = tk.Entry(self.tab_TDS, width=15)
        TDS_timeTxt.insert(0, "1e-6")
        TDS_timeTxt.grid(row=1, column=0, padx=10, pady=10)

        TDS_timeButton = tk.Button(
            self.tab_TDS,
            bg='grey',
            fg='white',
            text="Set Time Scale",
            command=set_time_scale
        )
        TDS_timeButton.grid(row=1, column=1, padx=10, pady=10)

    def create_measure_tab(self):
        """
        Create the Measurement tab with controls and protocol table.
        """
        self.tab_MEASURE = tk.Frame(self.tabControl, bg='#BBBBBB')
        self.tabControl.add(self.tab_MEASURE, text="Measure")
        self.create_measure_controls()

    def create_measure_controls(self):
        """
        Create controls for starting and cancelling measurements.
        """
        def run_measurement():
            if self.arduino.is_connected:
                self.load_protocol_from_script()
                self.read_table()
                self.stop_measurement.clear()
                self.measurement_thread = threading.Thread(target=self.measurement_loop, daemon=True)
                self.measurement_thread.start()
                self.start_btn.config(state='disabled')
                self.cancel_btn.config(state='normal')
                logging.info("Measurement started.")
            else:
                messagebox.showwarning("Arduino Not Connected", "Please initialize Arduino before starting measurements.")
                logging.warning("Attempted to start measurement without Arduino connection.")

        def cancel_measurement():
            if self.measurement_thread and self.measurement_thread.is_alive():
                self.stop_measurement.set()
                self.measurement_thread.join()
                self.start_btn.config(state='normal')
                self.cancel_btn.config(state='disabled')
                messagebox.showinfo("Cancelled", "Measurement process has been terminated.")
                logging.info("Measurement cancelled by user.")
            else:
                messagebox.showinfo("No Process", "No ongoing measurement process to cancel.")
                logging.info("No measurement process to cancel.")

        # Control Buttons
        control_frame = tk.Frame(self.tab_MEASURE, bg='#BBBBBB')
        control_frame.pack(pady=10)

        self.start_btn = tk.Button(
            control_frame,
            bg='green',
            fg='white',
            text="Start Measurement",
            command=run_measurement
        )
        self.start_btn.grid(row=0, column=0, padx=10, pady=10)

        self.cancel_btn = tk.Button(
            control_frame,
            bg='red',
            fg='white',
            text="Cancel Measurement",
            command=cancel_measurement,
            state='disabled'
        )
        self.cancel_btn.grid(row=0, column=1, padx=10, pady=10)

        # Protocol Script Editor
        script_frame = tk.LabelFrame(self.tab_MEASURE, text="Measurement Script", bg='#BBBBBB')
        script_frame.pack(pady=10, fill='both', expand=True, padx=10)

        self.script_text = tk.Text(script_frame, height=15)
        self.script_text.pack(side='left', fill='both', expand=True, padx=(0, 10), pady=10)

        # Insert default sample script
        default_script = (
            "# Sample Measurement Script\n"
            "# Format: Script,T,Y1,Y2,IMP,TDS-AV,NUM,TIME,on-on,off-on,on-off,load R,light\n"
            "INIT-TAS,,,,,,,,,,,\n"
            "LASER-TAS,2e-5,2e-1,1e-3,MEG,512,1,10,1,0,0,1,100\n"
            "INIT-TAS,,,,,,,,,,,\n"
            "LASER-TAS,2e-5,2e-2,1e-3,FIF,512,1,10,1,0,0,1,100\n"
            "INIT-TAS,,,,,,,,,,,\n"
        )
        self.script_text.insert(tk.END, default_script)

        # Scrollbar for the script editor
        scrollbar = tk.Scrollbar(script_frame, command=self.script_text.yview)
        scrollbar.pack(side='right', fill='y')
        self.script_text.config(yscrollcommand=scrollbar.set)

        # Load and Save Script Buttons
        script_buttons_frame = tk.Frame(self.tab_MEASURE, bg='#BBBBBB')
        script_buttons_frame.pack(pady=5)

        load_script_btn = tk.Button(
            script_buttons_frame,
            text="Load Script",
            command=self.load_script
        )
        load_script_btn.grid(row=0, column=0, padx=10, pady=5)

        save_script_btn = tk.Button(
            script_buttons_frame,
            text="Save Script",
            command=self.save_script
        )
        save_script_btn.grid(row=0, column=1, padx=10, pady=5)

        # Protocol Table
        table_frame = tk.Frame(self.tab_MEASURE)
        table_frame.pack(pady=10, fill='both', expand=True, padx=10)

        # Default protocol DataFrame (empty initially)
        df = pd.DataFrame(columns=[
            'Script', 'T', 'Y1', 'Y2', 'IMP', 'TDS-AV',
            'NUM', 'TIME', 'on-on', 'off-on', 'on-off', 'load R', 'light'
        ])

        self.protokollTab = pdt.Table(
            table_frame,
            dataframe=df,
            showtoolbar=True,
            showstatusbar=True
        )
        self.protokollTab.show()

    def load_script(self):
        """
        Load a measurement script from a file into the script editor.
        """
        filepath = filedialog.askopenfilename(filetypes=[("Script Files", "*.txt"), ("All Files", "*.*")])
        if not filepath:
            return
        try:
            with open(filepath, 'r') as file:
                script = file.read()
                self.script_text.delete('1.0', tk.END)
                self.script_text.insert(tk.END, script)
                logging.info(f"Loaded script from {filepath}")
        except Exception as e:
            messagebox.showerror("Load Script Error", f"Failed to load script: {e}")
            logging.error(f"Failed to load script from {filepath}: {e}")

    def save_script(self):
        """
        Save the current measurement script from the script editor to a file.
        """
        filepath = filedialog.asksaveasfilename(defaultextension=".txt",
                                                filetypes=[("Script Files", "*.txt"), ("All Files", "*.*")])
        if not filepath:
            return
        try:
            script = self.script_text.get('1.0', tk.END)
            with open(filepath, 'w') as file:
                file.write(script)
                logging.info(f"Saved script to {filepath}")
            messagebox.showinfo("Save Script", "Script saved successfully.")
        except Exception as e:
            messagebox.showerror("Save Script Error", f"Failed to save script: {e}")
            logging.error(f"Failed to save script to {filepath}: {e}")

    def read_table(self):
        """
        Read the protocol table and prepare for measurements.
        """
        self.df = self.protokollTab.model.df.copy()
        # Reset output files
        output_file = os.path.join(self.dirpath, "output")
        protokol_file = os.path.join(self.dirpath, "protokol.dat")
        open(output_file, 'w').close()
        open(protokol_file, 'w').close()
        logging.info("Protocol table read and output files reset.")

    def run_protokoll(self, line):
        """
        Run a specific line from the protocol table.
        """
        prot = ' '.join(map(str, self.df.iloc[line, :13])) + "\n"
        protokol_file = os.path.join(self.dirpath, "protokol.dat")
        try:
            with open(protokol_file, "w") as prot_file:
                prot_file.write(prot)
            logging.info(f"Protocol written for line {line}: {prot}")
        except Exception as e:
            messagebox.showerror("Protocol Error", f"Failed to write protocol: {e}")
            logging.error(f"Failed to write protocol for line {line}: {e}")
            return

        # Construct current run identifier
        self.currentRun = f"{self.df.iat[line, 0]}_t{self.df.iat[line, 1]}_y1{self.df.iat[line, 2]}_y2{self.df.iat[line, 3]}_{self.df.iat[line, 4]}_IRon_VISon"
        self.LastRun = self.currentRun
        logging.info(f"Running: {self.currentRun}")

        # Execute the measurement cycle
        success = self.osc_controller.run_measurement_cycle(self.currentRun, self.dirpath)
        if success:
            self.update_graphs()
        else:
            messagebox.showerror("Measurement Error", f"Measurement failed for {self.currentRun}.")
            logging.error(f"Measurement failed for {self.currentRun}.")

    def measurement_loop(self):
        """
        Loop through the protocol table and run each measurement.
        """
        protokollLength = self.df.shape[0]
        for line in range(self.runLine, protokollLength):
            if self.stop_measurement.is_set():
                logging.info("Measurement loop stopped by user.")
                break
            self.run_protokoll(line)
            self.runLine += 1

        self.start_btn.config(state='normal')
        self.cancel_btn.config(state='disabled')

        if not self.stop_measurement.is_set():
            messagebox.showinfo("Measurement Complete", "All measurements have been completed.")
            logging.info("All measurements have been completed.")
        self.runLine = 0

    def measurement_monitor(self):
        """
        Monitor the measurement process and refresh the GUI as needed.
        """
        self.root.after(1000, self.measurement_monitor)

    def update_graphs(self):
        """
        Update the graphs with the latest measurement data.
        """
        file1 = os.path.join(self.dirpath, f"{self.LastRun}_el_av.dat")
        file2 = os.path.join(self.dirpath, f"{self.LastRun}_op_av.dat")

        # Update Channel 1 Plot
        if os.path.isfile(file1):
            data = pd.read_csv(file1, delim_whitespace=True, header=None, names=['Time', 'EL'])
            self.line_top.set_data(data['Time'], data['EL'])
            self.ax_top.relim()
            self.ax_top.autoscale_view()
            self.canvasTop.draw()
            logging.info(f"Channel 1 plot updated for {self.LastRun}.")

        # Update Channel 2 Plot
        if os.path.isfile(file2):
            data = pd.read_csv(file2, delim_whitespace=True, header=None, names=['Time', 'OP'])
            self.line_mid.set_data(data['Time'], data['OP'])
            self.ax_mid.relim()
            self.ax_mid.autoscale_view()
            self.canvasMid.draw()
            logging.info(f"Channel 2 plot updated for {self.LastRun}.")

    def load_protocol_from_script(self):
        """
        Load measurement protocol from the script editor into the protocol table.
        """
        script = self.script_text.get('1.0', tk.END).strip()
        lines = script.split('\n')
        protocol_data = []
        for line in lines:
            if not line.strip() or line.startswith('#'):
                continue  # Skip empty lines and comments
            parts = line.split(',')
            if len(parts) != 13:
                logging.warning(f"Invalid script line format: {line}")
                continue
            protocol_data.append(parts)
        if protocol_data:
            self.df = pd.DataFrame(protocol_data, columns=[
                'Script', 'T', 'Y1', 'Y2', 'IMP', 'TDS-AV',
                'NUM', 'TIME', 'on-on', 'off-on', 'on-off', 'load R', 'light'
            ])
            self.protokollTab.updateModel(self.df)
            self.protokollTab.redraw()
            logging.info("Protocol table updated from script.")

if __name__ == "__main__":
    root = tk.Tk() #Cria Janela
    app = TAS_GUI(root) 
    root.mainloop() #Deixa a janela da interface sempre aberta