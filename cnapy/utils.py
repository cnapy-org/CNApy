''' CNApy utilities '''
from qtpy.QtCore import QObject, Qt, Signal, Slot, QTimer
from qtpy.QtWidgets import QMessageBox, QLineEdit, QTableWidget, QTableWidgetItem, \
                           QCompleter, QApplication, QFrame, QSizePolicy
from straindesign import lineq2list, linexpr2dict
import re

def BORDER_COLOR(HEX): # string that defines style sheet for changing the color of the module-box
    return "QGroupBox#EditModule "+\
                "{ border: 1px solid "+HEX+";"+\
                "  padding: 12 5 0 0 em ;"+\
                "  margin: 0 0 0 0 em};"

def BACKGROUND_COLOR(HEX,id): # string that defines style sheet for changing the color of the module-box
    return "QLineEdit#"+id+" "+\
                "{ background: "+HEX+"};"
                
def FONT_COLOR(HEX): # string that defines style sheet for changing the color of the module-box
    return "QLabel { color: "+HEX+"};"

def show_unknown_error_box(exstr):
    msgBox = QMessageBox()
    msgBox.setWindowTitle("Unknown Error!")
    msgBox.setTextFormat(Qt.RichText)

    msgBox.setText("<p>"+exstr+"</p><p><b> Please report the problem to:</b></p>\
    <p><a href='https://github.com/cnapy-org/CNApy/issues'>https://github.com/cnapy-org/CNApy/issues</a></p>")
    msgBox.setIcon(QMessageBox.Warning)
    msgBox.exec()


def turn_red(item):
    palette = item.palette()
    role = item.foregroundRole()
    palette.setColor(role, Qt.black)
    item.setPalette(palette)

    item.setStyleSheet("background: #ff9999")


def turn_white(item):
    palette = item.palette()
    role = item.foregroundRole()
    palette.setColor(role, Qt.black)
    item.setPalette(palette)

    item.setStyleSheet("background: white")


class SignalThrottler(QObject):
    def __init__(self, interval):
        QObject.__init__(self)
        self.timer = QTimer()
        self.timer.setInterval(interval)
        self.hasPendingEmission = False
        self.timer.timeout.connect(self.maybeEmitTriggered)

    def maybeEmitTriggered(self):
        if self.hasPendingEmission:
            self.emit_triggered()

    @Slot()
    def throttle(self):
        self.hasPendingEmission = True

        if not self.timer.isActive():
            self.timer.start()

    def emit_triggered(self):
        self.hasPendingEmission = False
        self.triggered.emit()

    @Slot()
    def finish(self):
        self.timer.stop()
        if self.hasPendingEmission:
            self.emit_triggered()

    triggered = Signal()
    timeoutChanged = Signal(int)
    timerTypeChanged = Signal(Qt.TimerType)

class QComplReceivLineEdit(QLineEdit):
    '''# does new completion after SPACE'''
    def __init__(self, sd_dialog, wordlist, check=True, is_constr=False):
        super().__init__("")
        self.sd_dialog = sd_dialog
        self.wordlist = wordlist
        self.completer = QCompleter(wordlist)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setWidget(self)
        self.textChanged.connect(self.text_changed)
        self.completer.activated.connect(self.complete_text)
        self.setObjectName("EditField")
        self.check = check
        self.is_constr = is_constr
        self.is_valid = None

    def text_changed(self, text):
        all_text = text
        text = all_text[:self.cursorPosition()]
        prefix = re.split('\s|,|-',text)[-1].strip()
        if prefix != '':
            self.completer.setCompletionPrefix(prefix)
            self.completer.complete()
        self.check_text(False)
        
    def complete_text(self, text):
        cursor_pos = self.cursorPosition()
        before_text = self.text()[:cursor_pos]
        after_text = self.text()[cursor_pos:]
        prefix_len = len(re.split('\s|,|-',before_text)[-1].strip())
        self.setText(before_text[:cursor_pos - prefix_len] + text + " " + after_text)
        self.setCursorPosition(cursor_pos - prefix_len + len(text) + 1)
    
    def skip_completion(self):
        self.completer.setCompletionPrefix('###') # dummy
    
    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.sd_dialog.active_receiver = self
    
    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.check_text(True)
    
    def check_text(self,final):
        if self.check:
            if self.text().strip() == "":
                self.setStyleSheet(BACKGROUND_COLOR("#ffffff",self.objectName()))
                self.textCorrect.emit(False)
                self.is_valid = None
                return None
            else:
                try:
                    if self.is_constr:
                        lineq2list([self.text()], self.wordlist)
                    else:
                        linexpr2dict(self.text(), self.wordlist)
                    if final:
                        self.setStyleSheet(BACKGROUND_COLOR("#ffffff",self.objectName()))
                    else:
                        self.setStyleSheet(BACKGROUND_COLOR("#f0fff1",self.objectName()))
                    self.is_valid = True
                    self.textCorrect.emit(True)
                    return True
                except:
                    if final:
                        self.setStyleSheet(BACKGROUND_COLOR("#fff0f0",self.objectName()))
                    else:
                        self.setStyleSheet(BACKGROUND_COLOR("#ffffff",self.objectName()))
                    self.is_valid = False
                    self.textCorrect.emit(False)
                    return False
                
    textCorrect = Signal(bool)
    

class QTableCopyable(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.key() == Qt.Key_C and (event.modifiers() & Qt.ControlModifier):
            copied_cells = sorted(self.selectedIndexes())
            copy_text = ''
            max_column = copied_cells[-1].column()
            for c in copied_cells:
                if self.item(c.row(), c.column()) is not None:
                    copy_text += self.item(c.row(), c.column()).text()
                    if c.column() == max_column:
                        copy_text += '\n'
                    else:
                        copy_text += '\t'
            QApplication.clipboard().setText(copy_text)
            
class QTableItem(QTableWidgetItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    def setEditable(self,b):
        f = self.flags()
        if b:
            self.setFlags(f|Qt.ItemIsEditable)
        else:
            self.setFlags(f&~Qt.ItemIsEditable)
            
    def setSelectable(self,b):
        f = self.flags()
        if b:
            self.setFlags(f|Qt.ItemIsSelectable)
        else:
            self.setFlags(f&~Qt.ItemIsSelectable)
            
    def setEnabled(self,b):
        f = self.flags()
        if b:
            self.setFlags(f|Qt.ItemIsEnabled)
        else:
            self.setFlags(f&~Qt.ItemIsEnabled)
            
class QHSeperationLine(QFrame):
  '''
  a horizontal seperation line\n
  '''
  def __init__(self):
    super().__init__()
    self.setMinimumWidth(1)
    self.setFixedHeight(20)
    self.setFrameShape(QFrame.HLine)
    self.setFrameShadow(QFrame.Sunken)
    self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
    return

class QVSeperationLine(QFrame):
  '''
  a vertical seperation line\n
  '''
  def __init__(self):
    super().__init__()
    self.setFixedWidth(20)
    self.setMinimumHeight(1)
    self.setFrameShape(QFrame.VLine)
    self.setFrameShadow(QFrame.Sunken)
    self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
    return