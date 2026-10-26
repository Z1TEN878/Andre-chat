 import kivy
kivy.require('2.1.0')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.core.window import Window

import threading
import datetime
import asyncio

try:
    import websockets
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False

SERVER_URL = "wss://retro-chat-76hm.onrender.com"

class ChatMessage(Label):
    def __init__(self, sender, text, **kwargs):
        time_now = datetime.datetime.now().strftime("%H:%M")
        if sender == "Система":
            msg = f"[{time_now}] *** {text} ***"
            color = (0.4, 0.4, 0.4, 1)
        else:
            avatar = f"[{sender[0].upper()}]" if sender else "[?]"
            msg = f"[{time_now}] {avatar} {sender}: {text}"
            color = (0, 0, 0, 1)
        super().__init__(
            text=msg,
            color=color,
            font_size="14sp",
            size_hint_y=None,
            halign="left",
            valign="top",
            text_size=(Window.width - 40, None),
            **kwargs
        )
        self.bind(texture_size=self.setter('size'))

class ChatLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', **kwargs)

        # Цвета
        self.bg_main = (0.56, 0.79, 0.98, 1)
        self.header_blue = (0.05, 0.28, 0.63, 1)
        self.chat_bg = (0.88, 0.96, 0.99, 1)
        self.btn_blue = (0.26, 0.65, 0.96, 1)
        self.color_offline = (0.83, 0.18, 0.18, 1)
        self.color_online = (0.30, 0.69, 0.31, 1)
        
        with self.canvas.before:
            Color(*self.bg_main)
            self.rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self.update_rect, size=self.update_rect)

        self.ws = None
        self.loop = None
        self.is_connected = False
        self.my_name = "Вы"

        # --- Верхняя панель ---
        self.top_bar = BoxLayout(size_hint_y=None, height="50dp", padding=5)
        with self.top_bar.canvas.before:
            self.status_color = Color(*self.color_offline) 
            self.top_rect = Rectangle(pos=self.top_bar.pos, size=self.top_bar.size)
        self.top_bar.bind(
            pos=lambda *a: setattr(self.top_rect, 'pos', self.top_bar.pos),
            size=lambda *a: setattr(self.top_rect, 'size', self.top_bar.size)
        )
        self.status_label = Label(text="Статус: Отключено", color=(1, 1, 1, 1), bold=True, font_size="16sp")
        self.top_bar.add_widget(self.status_label)
        self.add_widget(self.top_bar)

        # --- Чат ---
        self.scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        with self.scroll.canvas.before:
            Color(*self.chat_bg)
            self.scroll_rect = Rectangle(pos=self.scroll.pos, size=self.scroll.size)
        self.scroll.bind(
            pos=lambda *a: setattr(self.scroll_rect, 'pos', self.scroll.pos),
            size=lambda *a: setattr(self.scroll_rect, 'size', self.scroll.size)
        )
        self.chat_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5, padding=10)
        self.chat_box.bind(minimum_height=self.chat_box.setter('height'))
        self.scroll.add_widget(self.chat_box)
        self.add_widget(self.scroll)

        # --- Настройки ---
        self.settings_box = BoxLayout(orientation='vertical', size_hint_y=None, height="130dp", padding=5, spacing=3)
        with self.settings_box.canvas.before:
            Color(0.85, 0.92, 0.98, 1)
            self.settings_rect = Rectangle(pos=self.settings_box.pos, size=self.settings_box.size)
        self.settings_box.bind(
            pos=lambda *a: setattr(self.settings_rect, 'pos', self.settings_box.pos),
            size=lambda *a: setattr(self.settings_rect, 'size', self.settings_box.size)
        )

        name_row = BoxLayout(size_hint_y=None, height="40dp", spacing=5)
        name_row.add_widget(Label(text="Ник:", color=(0, 0, 0, 1), size_hint_x=0.2))
        self.name_entry = TextInput(
            text="Вы", multiline=False, size_hint_x=0.8,
            font_size="14sp", input_type='text', keyboard_suggestions=False
        )
        name_row.add_widget(self.name_entry)
        self.settings_box.add_widget(name_row)

        self.btn_connect = Button(
            text="Подключиться к облаку", size_hint_y=None, height="40dp",
            background_color=self.btn_blue, font_size="14sp"
        )
        self.btn_connect.bind(on_press=self.start_client_ws)
        self.settings_box.add_widget(self.btn_connect)

        self.btn_clear = Button(
            text="Очистить чат", size_hint_y=None, height="35dp",
            background_color=(0.39, 0.71, 0.96, 1), font_size="12sp"
        )
        self.btn_clear.bind(on_press=self.clear_chat)
        self.settings_box.add_widget(self.btn_clear)
        self.add_widget(self.settings_box)

        # --- Нижняя панель ввода ---
        self.bottom_bar = BoxLayout(size_hint_y=None, height="55dp", padding=5, spacing=5)
        self.msg_entry = TextInput(
            hint_text="Сообщение...", multiline=False, disabled=True,
            font_size="14sp", input_type='text', keyboard_suggestions=False
        )
        self.msg_entry.bind(on_text_validate=self.send_message)
        self.bottom_bar.add_widget(self.msg_entry)

        self.send_btn = Button(
            text="Отпр.", size_hint_x=None, width="65dp",
            disabled=True, background_color=self.color_online, font_size="14sp", bold=True
        )
        self.send_btn.bind(on_press=self.send_message)
        self.bottom_bar.add_widget(self.send_btn)
        self.add_widget(self.bottom_bar)

        self.add_message("Система", f"Адрес сервера: {SERVER_URL}")
        self.add_message("Система", "Введите Ник и нажмите 'Подключиться к облаку'.")
        if not WS_AVAILABLE:
            self.add_message("Система", "ВНИМАНИЕ: Библиотека websockets не установлена!")

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def add_message(self, sender, text):
        # Безопасно добавляем сообщение в UI потоке
        Clock.schedule_once(lambda dt: self._add_message_ui(sender, text))

    def _add_message_ui(self, sender, text):
        msg_widget = ChatMessage(sender, text)
        msg_widget.text_size = (self.width - 40, None)
        self.chat_box.add_widget(msg_widget)
        Clock.schedule_once(lambda dt: setattr(self.scroll, 'scroll_y', 0), 0.05)

    def clear_chat(self, instance):
        self.chat_box.clear_widgets()
        self.add_message("Система", "История чата очищена.")

    def set_connected_state(self, connected):
        self.is_connected = connected
        if connected:
            self.status_label.text = "Статус: В сети (Облако)"
            self.status_label.color = (0, 0, 0, 1) 
            self.status_color.rgba = self.color_online 
            self.msg_entry.disabled = False
            self.send_btn.disabled = False
            self.btn_connect.disabled = True
            self.name_entry.disabled = True
        else:
            self.status_label.text = "Статус: Отключено"
            self.status_label.color = (1, 1, 1, 1) 
            self.status_color.rgba = self.color_offline 
            self.msg_entry.disabled = True
            self.send_btn.disabled = True
            self.btn_connect.disabled = False
            self.name_entry.disabled = False

    # ==========================================
    # Логика WebSocket
    # ==========================================
    def start_client_ws(self, instance):
        if not WS_AVAILABLE:
            self.add_message("Система", "Установите библиотеку websockets через Pip!")
            return

        self.my_name = self.name_entry.text.strip()
        if not self.my_name:
            self.add_message("Система", "Введите Ник!")
            return

        self.btn_connect.disabled = True
        self.add_message("Система", "Подключение...")
        threading.Thread(target=self.run_ws_client, daemon=True).start()

    def run_ws_client(self):
        # Создаем новый цикл событий для этого потока
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        async def connect():
            try:
                # open_timeout=60 на случай, если Render "спит"
                async with websockets.connect(SERVER_URL, open_timeout=60) as websocket:
                    self.ws = websocket
                    Clock.schedule_once(lambda dt: self.set_connected_state(True))
                    self.add_message("Система", "✅ Успешное подключение к облаку!")

                    # Слушаем сообщения
                    async for message in websocket:
                        self.add_message("Собеседник", message)

            except Exception as e:
                self.add_message("Система", f"❌ Ошибка подключения: {e}")
            finally:
                self.ws = None
                Clock.schedule_once(lambda dt: self.set_connected_state(False))

        self.loop.run_until_complete(connect())

    def send_message(self, instance):
        text = self.msg_entry.text.strip()
        if text and self.is_connected and self.ws and self.loop:
            try:
                full_msg = f"{self.my_name}: {text}"
                # Безопасно отправляем в цикл событий
                asyncio.run_coroutine_threadsafe(self.ws.send(full_msg), self.loop)
                self.add_message(self.my_name, text)
                self.msg_entry.text = ""
            except Exception as e:
                self.add_message("Система", f"Ошибка отправки: {e}")
                self.set_connected_state(False)

class RetroMessengerApp(App):
    def build(self):
        self.title = "Ретро-Мессенджер"
        Window.clearcolor = (0.56, 0.79, 0.98, 1)
        return ChatLayout()

if __name__ == "__main__":
    RetroMessengerApp().run()