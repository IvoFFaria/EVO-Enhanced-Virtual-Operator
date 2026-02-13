"""
EVO - Enhanced Virtual Operator
HUD Overlay (status + last message + input opcional)

- Sempre visível: Estado + Última mensagem do EVO
- Opcional: Entrada de texto (modo expandido)
- Emite command_submitted(str) quando envias comando
"""

from PySide6 import QtCore, QtGui, QtWidgets


class EvoOverlay(QtWidgets.QWidget):
    command_submitted = QtCore.Signal(str)

    def __init__(self, app_name: str = "EVO"):
        super().__init__()
        self.app_name = app_name
        self._status_text = f"{self.app_name}: Standby"
        self._last_message = ""
        self._expanded = False

        self._init_window()
        self._build_ui()
        self._apply_layout_mode()

        self.show()

    # ---------------- Window ----------------

    def _init_window(self) -> None:
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        screen = QtGui.QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()

        self._w_compact = 520
        self._h_compact = 120

        self._w_expanded = 560
        self._h_expanded = 190

        margin = 18
        self.setGeometry(
            geo.right() - self._w_compact - margin,
            geo.top() + margin,
            self._w_compact,
            self._h_compact,
        )

    # ---------------- UI ----------------

    def _build_ui(self) -> None:
        self._root = QtWidgets.QFrame(self)
        self._root.setObjectName("root")

        # Status (linha 1)
        self._title = QtWidgets.QLabel(self._root)
        self._title.setObjectName("title")
        self._title.setText(self._status_text)

        # Última mensagem (linha 2)
        self._message = QtWidgets.QLabel(self._root)
        self._message.setObjectName("message")
        self._message.setText("")  # vazio no arranque
        self._message.setWordWrap(True)

        # Input row
        self._input = QtWidgets.QLineEdit(self._root)
        self._input.setObjectName("input")
        self._input.setPlaceholderText("Escreve um comando… (Enter)")
        self._input.returnPressed.connect(self._on_submit)

        self._send = QtWidgets.QPushButton("Enviar", self._root)
        self._send.setObjectName("send")
        self._send.clicked.connect(self._on_submit)

        # Hint
        self._hint = QtWidgets.QLabel(self._root)
        self._hint.setObjectName("hint")
        self._hint.setText("Clique no overlay para abrir/fechar entrada de texto")

        # Layouts
        root_layout = QtWidgets.QVBoxLayout(self._root)
        root_layout.setContentsMargins(16, 14, 16, 14)
        root_layout.setSpacing(10)

        root_layout.addWidget(self._title)
        root_layout.addWidget(self._message)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._input, 1)
        row.addWidget(self._send, 0)

        root_layout.addLayout(row)
        root_layout.addWidget(self._hint)

        # Styling
        self.setStyleSheet("""
        #root {
            background-color: rgba(15,15,15,160);
            border: 1px solid rgba(255,255,255,40);
            border-radius: 16px;
        }
        #title {
            color: rgba(255,255,255,230);
            font-family: "Segoe UI";
            font-size: 13px;
            font-weight: 700;
        }
        #message {
            color: rgba(255,255,255,200);
            font-family: "Segoe UI";
            font-size: 12px;
        }
        #input {
            background-color: rgba(30,30,30,200);
            border: 1px solid rgba(255,255,255,40);
            border-radius: 10px;
            padding: 8px 10px;
            color: rgba(255,255,255,230);
            font-family: "Segoe UI";
            font-size: 12px;
        }
        #send {
            background-color: rgba(255,255,255,22);
            border: 1px solid rgba(255,255,255,40);
            border-radius: 10px;
            padding: 8px 14px;
            color: rgba(255,255,255,230);
            font-family: "Segoe UI";
            font-size: 12px;
            font-weight: 700;
        }
        #send:hover { background-color: rgba(255,255,255,28); }
        #send:pressed { background-color: rgba(255,255,255,18); }

        #hint {
            color: rgba(255,255,255,140);
            font-family: "Segoe UI";
            font-size: 11px;
        }
        """)

    def _apply_layout_mode(self) -> None:
        screen = QtGui.QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        margin = 18

        if self._expanded:
            w, h = self._w_expanded, self._h_expanded
            self._input.show()
            self._send.show()
            self._hint.show()
            self._input.setFocus()
        else:
            w, h = self._w_compact, self._h_compact
            self._input.hide()
            self._send.hide()
            self._hint.hide()

        self.setGeometry(
            geo.right() - w - margin,
            geo.top() + margin,
            w,
            h,
        )
        self._root.setGeometry(0, 0, w, h)

    # ---------------- Public API ----------------

    def set_status(self, text: str) -> None:
        self._status_text = text
        self._title.setText(text)

    def set_last_message(self, text: str) -> None:
        """
        Mostra a última “fala” / resposta do EVO no overlay.
        """
        self._last_message = (text or "").strip()
        self._message.setText(self._last_message)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        self._apply_layout_mode()

    def toggle_expanded(self) -> None:
        self._expanded = not self._expanded
        self._apply_layout_mode()

    # ---------------- Events ----------------

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        self.toggle_expanded()
        event.accept()

    def _on_submit(self) -> None:
        text = (self._input.text() or "").strip()
        if not text:
            return
        self._input.clear()
        self.command_submitted.emit(text)
