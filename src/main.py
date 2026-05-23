from PySide6.QtWidgets import QApplication
from src.app.window import MainWindow


def main():
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == '__main__':
    main()
