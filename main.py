import requests
from bs4 import BeautifulSoup
import socket
import struct
import fcntl
import threading
from kivy.lang import Builder
from kivymd.app import MDApp
from kivymd.uix.list import TwoLineListItem
from kivy.clock import mainthread
import re
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.list import TwoLineAvatarListItem, ImageLeftWidget
from kivy.properties import StringProperty


# Global variable to store selected PlayStation IP
PS3IP = None


class PyWebman(MDApp):
    game_count = StringProperty('')


    def build(self):
        self.theme_cls.theme_style = "Light"
        return Builder.load_file('main.kv')

    def switch_screen(self, screen_name):
        self.root.ids.screen_manager.current = screen_name
        self.root.ids.nav_drawer.set_state("close")

    def open_dialog(self, title, text):
        """ Function to open a dialog with customizable title and text. """
        dialog = MDDialog(
            title=title,
            text=text,
            size_hint=(0.8, 0.2),
            buttons=[
                MDFlatButton(
                    text="OK", on_release=lambda x: dialog.dismiss()
                )
            ],
        )
        dialog.open()

    def add_ps3_dialog(self):
        """ Opens a dialog with an input field to manually add an IP address. """
        self.ip_input_dialog = MDDialog(
            title="Add PlayStation IP",
            type="custom",
            content_cls=MDTextField(
                hint_text="Enter PlayStation IP Address",
                id="ip_input_field",  # Assign an ID for easy access
                multiline=False,
            ),
            buttons=[
                MDFlatButton(
                    text="CANCEL", on_release=lambda x: self.ip_input_dialog.dismiss()
                ),
                MDFlatButton(
                    text="ADD", on_release=self.add_manual_ip
                ),
            ],
        )
        self.ip_input_dialog.open()

    def add_manual_ip(self, *args):
        """ Retrieve input from the dialog, validate, and add the IP to ps_list. """
        ip_field = self.ip_input_dialog.content_cls

        # Get the input IP address from the dialog
        input_ip = ip_field.text.strip()

        # Validate the IP address format (basic validation)
        if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', input_ip):
            # Add to ps_list
            self.add_playstation_item(input_ip, "Manually Added PlayStation")
            self.ip_input_dialog.dismiss()
        else:
            # Show an error message if the IP is invalid
            self.open_dialog(title="Invalid IP", text="Please enter a valid IP address.")


    def get_local_ip(self):
        """ Get the local IP address by creating a dummy connection to an external server. """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # This doesn't actually connect to the server, just opens a socket
            s.connect(("8.8.8.8", 80))
            ip_address = s.getsockname()[0]
            s.close()
            return ip_address
        except Exception as e:
            print(f"Error getting local IP: {e}")
            return None

    def get_subnet_mask(self, ifname):
        """ Get the subnet mask for the given interface using ioctl. """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Use ioctl to retrieve the subnet mask
            subnet_mask = socket.inet_ntoa(fcntl.ioctl(
                s.fileno(),
                0x891b,  # SIOCGIFNETMASK
                struct.pack('256s', ifname[:15].encode('utf-8'))
            )[20:24])
            return subnet_mask
        except Exception as e:
            print(f"Error getting subnet mask: {e}")
            return None

    def get_subnet(self):
        ip_address = self.get_local_ip()
        if ip_address is None:
            return None

        # Assuming eth0 or wlan0 as the default interface, adjust based on your environment.
        # Use your specific network interface here (e.g., 'eth0', 'wlan0').
        interface = 'wlan0'  # Change if necessary

        subnet_mask = self.get_subnet_mask(interface)
        if subnet_mask is None:
            return None

        # Convert IP and Subnet Mask to binary form
        ip_binary = struct.unpack('>I', socket.inet_aton(ip_address))[0]
        mask_binary = struct.unpack('>I', socket.inet_aton(subnet_mask))[0]

        # Calculate the network address (subnet)
        subnet_binary = ip_binary & mask_binary
        subnet = socket.inet_ntoa(struct.pack('>I', subnet_binary))

        # Return the subnet without the last octet (e.g., '192.168.1')
        return '.'.join(subnet.split('.')[:-1])

    def check_wman_mod(self, ip):
        try:
            url = f"http://{ip}"
            response = requests.get(url, timeout=2)
            soup = BeautifulSoup(response.content, 'html.parser')

            if soup.title and 'wman mod' in soup.title.string.lower():
                self.add_playstation_item(ip, soup.title.string)
        except requests.exceptions.RequestException:
            pass

    def scan_subnet(self):
        self.root.ids.ps_list.clear_widgets()  # Clear list before scanning
        subnet = self.get_subnet()
        if not subnet:
            print("Failed to determine subnet.")
            return

        threads = []

        for i in range(1, 255):
            ip = f"{subnet}.{i}"
            t = threading.Thread(target=self.check_wman_mod, args=(ip,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

    @mainthread
    def add_playstation_item(self, ip, title):
        item = TwoLineListItem(
            text=f"PlayStation Found: {ip}",
            secondary_text=title,
            on_release=lambda x=ip: self.set_ps3_ip(ip)
        )
        self.root.ids.ps_list.add_widget(item)

    def set_ps3_ip(self, ip):
        global PS3IP
        PS3IP = ip
        self.root.ids.selected_ps3ip.text = str(PS3IP)
        self.get_info(PS3IP)
        self.get_games()
        self.webman('popup.ps3/Connected to PyWebman&snd=0')
        print(f"Selected PlayStation IP: {PS3IP}")

    def get_info(self, ip):
        try:
            response = requests.get(f'http://{ip}/cpursx.ps3?/sman.ps3')
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract data
            title = soup.find('title').text.strip()

            # Function to find text in a tag containing a specific keyword
            def find_text(keyword):
                tag = soup.find(lambda tag: tag.name == 'a' and keyword in tag.text)
                return tag.text.strip() if tag else 'Not found'

            cpu = find_text('CPU:')
            mem = find_text('MEM:')
            hdd = find_text('HDD:')

            # Extract NAND Firmware version from <h2> tag
            nand_firmware_tag = soup.find('h2')
            nand_firmware = nand_firmware_tag.text.strip() if nand_firmware_tag else 'Not found'

            # Regex for firmware version (e.g., "4.91 CEX")
            firmware_regex = r"Firmware:\s*([\d.]+\s\w+)"
            firmware_match = re.search(firmware_regex, nand_firmware)
            firmware = firmware_match.group(1) if firmware_match else None

            # Regex for PS3HEN version (e.g., "PS3HEN 3.3.0")
            hen_regex = r"PS3HEN\s*([\d.]+)"
            hen_match = re.search(hen_regex, nand_firmware)
            hen_version = hen_match.group(0) if hen_match else None

            # Output
            print("Firmware:", firmware)
            print("HEN Version:", hen_version)

            self.root.ids.system_info_webman.text = title
            self.root.ids.system_info_mem.text = mem
            self.root.ids.system_info_hdd.text = hdd
            self.root.ids.system_info_nand.text = f'Firmware: {firmware}'

            # Print the results
            print(f"Title: {title}")
            print(f"CPU/RSX: {cpu}")
            print(f"MEM: {mem}")
            print(f"HDD: {hdd}")
            print(f"NAND Firmware version: {nand_firmware}")

            if  'Not found' in nand_firmware:
                self.open_dialog(title='ERROR', text='Webman Not Found')
        except:
            self.open_dialog(title='ERROR', text='Webman Not Found')


    def get_games(self):
        """ Fetch and display the list of games from the PlayStation """
        try:
            #url = f'http://{PS3IP}/sman.ps3?PS3ISO'
            url = f'http://{PS3IP}/sman.ps3?'
            response = requests.get(url)
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')

            # Find all game containers (div with class 'gc')
            games = soup.find_all('div', class_='gc')

            # Clear the game list before populating
            self.root.ids.game_list.clear_widgets()

            self.game_count = str(len(games))

            for game in games:
                # Extract the mount link (anchor tag within the div)
                mount_link = game.find('a')['href']

                # Extract the game title (anchor tag within the div with class 'gn')
                title = game.find('div', class_='gn').find('a').text.strip()

                # Extract the image link (img tag within the div with class 'ic')
                image_link = game.find('img')['src']

                # Adjust image link to be absolute if necessary
                if image_link.startswith('/'):
                    image_link = f'http://{PS3IP}{image_link}'

                # Add each game as a TwoLineAvatarListItem
                self.add_game_item(title, mount_link, image_link)

        except requests.exceptions.RequestException as e:
            print(f"Error fetching games: {e}")
            self.open_dialog(title="ERROR", text="Failed to retrieve games.")

    @mainthread
    def add_game_item(self, title, mount_link, image_link):
        """ Create and add a TwoLineAvatarListItem for each game """
        avatar = ImageLeftWidget(source=image_link)

        item = TwoLineAvatarListItem(
            text=title,
            secondary_text=f"Mount: {mount_link}",
            on_release=lambda x=mount_link: self.mount_game(mount_link)
        )
        item.add_widget(avatar)  # Add the avatar to the list item
        self.root.ids.game_list.add_widget(item)

    def mount_game(self, mount_link):
        """ Function to mount the selected game using the mount link """
        try:
            requests.get(f'http://{PS3IP}/{mount_link}')
            self.open_dialog(title="Success", text="Game mounted successfully!")
        except requests.exceptions.RequestException:
            self.open_dialog(title="ERROR", text="Failed to mount the game.")



    def webman(self, command):
        try:
            requests.get(f'http://{PS3IP}/{command}')
        except:
            self.open_dialog(title='ERROR', text='Please Connect to Console First!')

    def command_refresh(self):
        self.webman('refresh.ps3')

    def command_eject(self):
        self.webman('eject.ps3')

    def command_insert(self):
        self.webman('insert.ps3')

    def command_unmount(self):
        self.webman('/mount.ps3/unmount')

    def command_restart(self):
        self.webman('restart.ps3')

    def command_shutdown(self):
        self.webman('shutdown.ps3')


PyWebman().run()
