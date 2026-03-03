import sys
import asyncio
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from sopotek_trading.frontend.ui.app_controller import AppController

if __name__ == "__main__":

    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    controller = AppController()

    controller.show()

    with loop:
        loop.run_forever()