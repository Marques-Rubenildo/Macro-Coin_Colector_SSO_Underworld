import threading, time, sys, ctypes, math
import numpy as np
import win32api, win32con, win32gui
from PIL import ImageGrab
import cv2

# Config
running = False
stop_event = threading.Event()
overlay_instance = None
worker_thread = None

SAVE_DEBUG_EVERY = 2.0  # segundos
last_debug_save = 0.0

# Cor alvo em BGR (OpenCV usa BGR) para #03b733
TARGET_COLOR = np.array([51, 183, 3])
TOLERANCE = np.array([20, 20, 20])  # ajuste conforme necessário

def run_as_admin():
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return True
    except:
        return False

    params = " ".join([f'"{arg}"' for arg in sys.argv])
    try:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1
        )
    except Exception as e:
        print(f"Erro ao tentar elevar privilégios: {e}")
        return False

    sys.exit(0)

def get_game_hwnd():
    return win32gui.FindWindow(None, "Cavaleiros do Zodíaco -Underworld-Batalha pela Ilha Flutuante")

def get_game_rect():
    hwnd = get_game_hwnd()
    return win32gui.GetWindowRect(hwnd) if hwnd else None

def bring_game_to_front(hwnd):
    if hwnd:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        win32gui.BringWindowToTop(hwnd)

def get_mouse_pos():
    return win32api.GetCursorPos()

def move_mouse(x,y):
    win32api.SetCursorPos((x,y))

def click_left(x=None,y=None):
    if x is not None and y is not None:
        win32api.SetCursorPos((x,y))
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0,0,0,0)
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0,0,0,0)

######################################################################################
#                                  Teclas                                            #
######################################################################################

def press_alt_h():
    KEYEVENTF_SCANCODE=0x0008; KEYEVENTF_KEYUP=0x0002
    SC_ALT=0x38  # scancode da tecla 'ALT'
    SC_H=0x23    # scancode da tecla 'L'
    ctypes.windll.user32.keybd_event(0, SC_ALT, KEYEVENTF_SCANCODE, 0)
    time.sleep(0.2)
    ctypes.windll.user32.keybd_event(0, SC_H, KEYEVENTF_SCANCODE, 0)
    ctypes.windll.user32.keybd_event(0, SC_H, KEYEVENTF_SCANCODE|KEYEVENTF_KEYUP, 0)
    ctypes.windll.user32.keybd_event(0, SC_ALT, KEYEVENTF_SCANCODE|KEYEVENTF_KEYUP, 0)

def press_alt_l():
    KEYEVENTF_SCANCODE=0x0008; KEYEVENTF_KEYUP=0x0002
    SC_ALT=0x38 # scancode da tecla 'ALT'
    SC_H=0x26   # scancode da tecla 'H'
    ctypes.windll.user32.keybd_event(0, SC_ALT, KEYEVENTF_SCANCODE, 0)
    time.sleep(0.2)
    ctypes.windll.user32.keybd_event(0, SC_H, KEYEVENTF_SCANCODE, 0)
    ctypes.windll.user32.keybd_event(0, SC_H, KEYEVENTF_SCANCODE|KEYEVENTF_KEYUP, 0)
    ctypes.windll.user32.keybd_event(0, SC_ALT, KEYEVENTF_SCANCODE|KEYEVENTF_KEYUP, 0)

def press_key_1():
    KEYEVENTF_SCANCODE = 0x0008
    KEYEVENTF_KEYUP = 0x0002
    SC_1 = 0x02  # scancode da tecla '1'

    # Pressiona a tecla 1
    ctypes.windll.user32.keybd_event(0, SC_1, KEYEVENTF_SCANCODE, 0)
    # Solta a tecla 1
    ctypes.windll.user32.keybd_event(0, SC_1, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0)

def find_gold_positions():
    global last_debug_save

    rect = get_game_rect()
    if rect:
        left, top, right, bottom = rect
        pil_img = ImageGrab.grab(bbox=rect)
    else:
        left, top = 0, 0
        pil_img = ImageGrab.grab()

    img_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    # cria máscara para pixels dentro da faixa de cor alvo
    lower = np.clip(TARGET_COLOR - TOLERANCE, 0, 255)
    upper = np.clip(TARGET_COLOR + TOLERANCE, 0, 255)
    mask = cv2.inRange(img_bgr, lower, upper)

    coords = []
    points = cv2.findNonZero(mask)
    if points is not None:
        # opcional: reduzir número de pontos (ex.: amostragem a cada N pixels)
        for p in points:
            x, y = p[0]
            coords.append((left + x, top + y))

    # debug throttle
    now = time.time()
    if now - last_debug_save >= SAVE_DEBUG_EVERY:
        last_debug_save = now
        img_dbg = img_bgr.copy()
        if points is not None:
            for p in points[:2000]:  # limitar desenho para evitar arquivos enormes
                x, y = p[0]
                cv2.circle(img_dbg, (x, y), 2, (0,255,0), -1)
        cv2.imwrite("frame_debug_detected.png", img_dbg)

    return coords

def process_coordinates():
    pending_target = None
    last_clicked = None
    last_click_time = None
    DIST_DUP = 20
    CLICK_DELAY = 3.5
    NO_CLICK_TIMEOUT = 10.0

    while running and not stop_event.is_set():
        coords = find_gold_positions()

        # se passaram mais de 10s sem clique, retorna ao estado de busca (tecla 1)
        if last_click_time and (time.time() - last_click_time) >= NO_CLICK_TIMEOUT:
            print("[INFO] Nenhum clique em 10s, retornando ao estado de busca...")
            return  # sai da função e volta para o main_loop()

        if last_clicked and coords:
            coords = [c for c in coords if math.hypot(c[0]-last_clicked[0], c[1]-last_clicked[1]) >= DIST_DUP]

        if not coords and pending_target is None:
            time.sleep(0.05)
            continue

        if pending_target is None and coords:
            mx, my = get_mouse_pos()
            first = min(coords, key=lambda c: math.hypot(c[0]-mx, c[1]-my))
            move_mouse(first[0], first[1])
            click_left(first[0], first[1])
            last_clicked = first
            last_click_time = time.time()

            next_coords = [c for c in coords if math.hypot(c[0]-first[0], c[1]-first[1]) >= DIST_DUP]
            pending_target = min(next_coords, key=lambda c: math.hypot(c[0]-first[0], c[1]-first[1])) if next_coords else None
        else:
            elapsed = time.time() - last_click_time if last_click_time else 0.0
            if elapsed >= CLICK_DELAY:
                current = find_gold_positions()
                if current:
                    mx, my = get_mouse_pos()
                    target = min(current, key=lambda c: math.hypot(c[0]-mx, c[1]-my))
                    move_mouse(target[0], target[1])
                    click_left(target[0], target[1])
                    last_clicked = target
                    last_click_time = time.time()

                    coords = find_gold_positions()
                    coords = [c for c in coords if math.hypot(c[0]-last_clicked[0], c[1]-last_clicked[1]) >= DIST_DUP]
                    pending_target = min(coords, key=lambda c: math.hypot(c[0]-last_clicked[0], c[1]-last_clicked[1])) if coords else None
                else:
                    pending_target = None
            else:
                time.sleep(0.05)

def main_loop():
    while running and not stop_event.is_set():
        coords = find_gold_positions()
        if not coords:
            press_key_1()
            time.sleep(0.2)
            continue
        process_coordinates()

def wnd_proc(hwnd, msg, wparam, lparam):
    try:
        if msg == win32con.WM_HOTKEY:
            if wparam == 1:  # F8 toggle
                if not running:
                    game_hwnd = get_game_hwnd()
                    if game_hwnd:
                        bring_game_to_front(game_hwnd)
                        time.sleep(0.2)
                        press_alt_h()
                        press_alt_l()
                        start()
                else: # Neste bloco, caso a tecla F8 seja pressionada novamente, as funções press_alt_h e press_alt_l são chamadas novamente
                    press_alt_h()
                    press_alt_l()
                    stop()
            elif wparam == 2:  # F1 para fechar o programa e parar o processo
                press_alt_h()
                press_alt_l()
                stop()
                win32gui.PostQuitMessage(0)
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
    except Exception as e:
        print(f"[WNDPROC ERROR] {e}")
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

def start():
    global running, worker_thread
    running = True
    stop_event.clear()
    worker_thread = threading.Thread(target=main_loop, daemon=True)
    worker_thread.start()
    print("[INFO] Script ligado.")

def stop():
    global running, worker_thread
    running = False
    stop_event.set()
    if worker_thread and worker_thread.is_alive():
        worker_thread.join(timeout=1.5)
    worker_thread = None
    print("[INFO] Script desligado.")

def create_message_window():
    hInstance = win32api.GetModuleHandle()
    className = "HotkeyListenerStable"
    wc = win32gui.WNDCLASS()
    wc.lpfnWndProc = wnd_proc
    wc.lpszClassName = className
    wc.hInstance = hInstance
    win32gui.RegisterClass(wc)
    hwnd = win32gui.CreateWindow(className, "", 0, 0,0,0,0, 0,0, hInstance, None)
    return hwnd

if __name__ == "__main__":
    run_as_admin()  # garante execução como administrador
    hwnd = create_message_window()
    win32gui.RegisterHotKey(hwnd, 1, win32con.MOD_NOREPEAT, win32con.VK_F8)
    win32gui.RegisterHotKey(hwnd, 2, win32con.MOD_NOREPEAT, win32con.VK_F1)
    try:
        win32gui.PumpMessages()
    finally:
        win32gui.UnregisterHotKey(hwnd, 1)
        win32gui.UnregisterHotKey(hwnd, 2)
