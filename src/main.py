import asyncio
import sys
import traceback

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop
from frontend.ui.app_controller import AppController




app = QApplication(sys.argv)

loop = QEventLoop(app)
asyncio.set_event_loop(loop)

window = AppController()
window.setIconSize(QSize(48, 48))
if __name__ == "__main__":
 window.setWindowIcon(QIcon("./assets/logo.ico"))
 window.setWindowIconText("Sopotek Trading AI Platform")
 window.setWindowTitle("Sopotek Trading AI")

 window.show()

with loop:
    loop.run_forever()

