import os
import sys
import time
import ctypes
from ctypes import *
from datetime import datetime

# Structs and Constants
LLONG = c_int64
DWORD = c_uint32
WORD = c_uint16
BYTE = c_ubyte
BOOL = c_int

class NET_TIME(Structure):
    _fields_ = [
        ("dwYear", DWORD),
        ("dwMonth", DWORD),
        ("dwDay", DWORD),
        ("dwHour", DWORD),
        ("dwMinute", DWORD),
        ("dwSecond", DWORD)
    ]
    
    @classmethod
    def from_string(cls, dt_str):
        # Format: "YYYY-MM-DD HH:MM:SS"
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return cls(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)

    def to_datetime(self):
        try:
            return datetime(self.dwYear, self.dwMonth, self.dwDay, self.dwHour, self.dwMinute, self.dwSecond)
        except ValueError:
            return None

    def __str__(self):
        dt = self.to_datetime()
        return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "Invalid Time"

class NET_DEVICEINFO(Structure):
    _fields_ = [
        ("sSerialNumber", BYTE * 48),
        ("byAlarmInPortNum", BYTE),
        ("byAlarmOutPortNum", BYTE),
        ("byDiskNum", BYTE),
        ("byDVRType", BYTE),
        ("byChanNum", BYTE)
    ]

class NET_RECORDFILE_INFO(Structure):
    _fields_ = [
        ("ch", c_uint32),
        ("filename", c_char * 124),
        ("framenum", c_uint32),
        ("size", c_uint32), # KB
        ("starttime", NET_TIME),
        ("endtime", NET_TIME),
        ("driveno", c_uint32),
        ("startcluster", c_uint32),
        ("nRecordFileType", BYTE),
        ("bImportantRecID", BYTE),
        ("bHint", BYTE),
        ("bRecType", BYTE)
    ]

class IntelbrasDVR:
    def __init__(self, dll_path=None):
        self.sdk = None
        self.login_id = 0
        self._load_sdk(dll_path)
        self._init_sdk()

    def _load_sdk(self, dll_path=None):
        # If no path is specified, check standard SIM Next installation folders
        dll_dirs = []
        if dll_path:
            dll_dirs.append(dll_path)
        else:
            dll_dirs.extend([
                r"C:\Program Files\Intelbras\SIMNext\SIM Next",
                r"C:\Program Files (x86)\Intelbras\SIMNext\SIM Next"
            ])
            
        loaded = False
        for d in dll_dirs:
            if os.path.exists(d) and os.path.exists(os.path.join(d, "dhnetsdk.dll")):
                try:
                    os.add_dll_directory(d)
                    dll_file = os.path.join(d, "dhnetsdk.dll")
                    self.sdk = ctypes.windll.LoadLibrary(dll_file)
                    print(f"Loaded NetSDK DLL from: {d}")
                    loaded = True
                    break
                except Exception as e:
                    print(f"Failed to load from {d}: {e}")
                    
        if not loaded:
            raise RuntimeError("Could not find or load dhnetsdk.dll. Please specify the dll_path to the folder containing the SIM Next native DLLs.")

        # Setup ctypes argtypes/restypes
        self.sdk.CLIENT_Init.argtypes = [c_void_p, c_void_p]
        self.sdk.CLIENT_Init.restype = BOOL
        self.sdk.CLIENT_Cleanup.argtypes = []
        self.sdk.CLIENT_Cleanup.restype = None
        
        self.sdk.CLIENT_LoginEx.argtypes = [c_char_p, WORD, c_char_p, c_char_p, c_int, c_void_p, POINTER(NET_DEVICEINFO), POINTER(c_int)]
        self.sdk.CLIENT_LoginEx.restype = LLONG
        
        self.sdk.CLIENT_Logout.argtypes = [LLONG]
        self.sdk.CLIENT_Logout.restype = BOOL
        
        self.sdk.CLIENT_FindFile.argtypes = [LLONG, c_int, c_int, c_char_p, POINTER(NET_TIME), POINTER(NET_TIME), BOOL, c_int]
        self.sdk.CLIENT_FindFile.restype = LLONG
        
        self.sdk.CLIENT_FindNextFile.argtypes = [LLONG, POINTER(NET_RECORDFILE_INFO)]
        self.sdk.CLIENT_FindNextFile.restype = c_int
        
        self.sdk.CLIENT_FindClose.argtypes = [LLONG]
        self.sdk.CLIENT_FindClose.restype = BOOL
        
        self.sdk.CLIENT_DownloadByTime.argtypes = [LLONG, c_int, c_int, POINTER(NET_TIME), POINTER(NET_TIME), c_char_p, c_void_p, c_void_p]
        self.sdk.CLIENT_DownloadByTime.restype = LLONG
        
        self.sdk.CLIENT_DownloadByRecordFile.argtypes = [LLONG, POINTER(NET_RECORDFILE_INFO), c_char_p, c_void_p, c_void_p]
        self.sdk.CLIENT_DownloadByRecordFile.restype = LLONG
        
        self.sdk.CLIENT_GetDownloadPos.argtypes = [LLONG, POINTER(c_int), POINTER(c_int)]
        self.sdk.CLIENT_GetDownloadPos.restype = BOOL
        
        self.sdk.CLIENT_StopDownload.argtypes = [LLONG]
        self.sdk.CLIENT_StopDownload.restype = BOOL
        
        self.sdk.CLIENT_GetLastError.argtypes = []
        self.sdk.CLIENT_GetLastError.restype = DWORD

    def _init_sdk(self):
        res = self.sdk.CLIENT_Init(None, 0)
        if not res:
            raise RuntimeError("CLIENT_Init failed. Could not initialize NetSDK.")

    def login(self, host, port, username, password):
        info = NET_DEVICEINFO()
        err = c_int(0)
        
        print(f"Logging in to {host}:{port} as {username}...")
        self.login_id = self.sdk.CLIENT_LoginEx(
            host.encode('utf-8'), 
            port, 
            username.encode('utf-8'), 
            password.encode('utf-8'), 
            0, # TCP standard login
            None, 
            byref(info), 
            byref(err)
        )
        
        if self.login_id == 0:
            last_err = self.sdk.CLIENT_GetLastError()
            raise RuntimeError(f"Login failed. Error Code: {err.value}, SDK Error: {last_err}")
            
        sn_str = bytes(info.sSerialNumber).decode('ascii', errors='ignore').strip('\x00')
        print(f"Login SUCCESS. Handles: {self.login_id} | Serial Number: {sn_str} | Channels: {info.byChanNum}")
        return {
            "serial_number": sn_str,
            "channels": info.byChanNum,
            "disks": info.byDiskNum,
            "alarm_in": info.byAlarmInPortNum,
            "alarm_out": info.byAlarmOutPortNum
        }

    def logout(self):
        if self.login_id != 0:
            self.sdk.CLIENT_Logout(self.login_id)
            self.login_id = 0
            print("Logged out.")

    def search_recordings(self, channel, start_time_str, end_time_str, record_type=0):
        """
        Searches recordings for a given channel and time range.
        record_type: 0 for general/regular recordings, 2 for motion detection.
        """
        if self.login_id == 0:
            raise RuntimeError("Not logged in.")

        tm_start = NET_TIME.from_string(start_time_str)
        tm_end = NET_TIME.from_string(end_time_str)
        
        print(f"Searching Channel {channel} for {start_time_str} to {end_time_str} (Type: {record_type})...")
        find_handle = self.sdk.CLIENT_FindFile(
            self.login_id, 
            channel, 
            record_type, 
            None, 
            byref(tm_start), 
            byref(tm_end), 
            False, 
            3000
        )
        
        if find_handle == 0:
            last_err = self.sdk.CLIENT_GetLastError()
            print(f"Search query failed. SDK Error: {last_err}")
            return []

        results = []
        try:
            while True:
                f_info = NET_RECORDFILE_INFO()
                res = self.sdk.CLIENT_FindNextFile(find_handle, byref(f_info))
                if res == 1:
                    filename = f_info.filename.decode('utf-8', errors='ignore')
                    results.append({
                        "ch": f_info.ch,
                        "filename": filename,
                        "size_kb": f_info.size,
                        "size_mb": f_info.size / 1024.0,
                        "starttime": str(f_info.starttime),
                        "endtime": str(f_info.endtime),
                        "recordfile_info_struct": f_info # Keep struct for direct download
                    })
                elif res == 0:
                    # End of files
                    break
                else:
                    last_err = self.sdk.CLIENT_GetLastError()
                    print(f"Error reading next file. SDK Error: {last_err}")
                    break
        finally:
            self.sdk.CLIENT_FindClose(find_handle)
            
        print(f"Search complete. Found {len(results)} files.")
        return results

    def download_file(self, file_info, output_path, progress_callback=None):
        """
        Downloads a full recording block using a NET_RECORDFILE_INFO structure.
        """
        if self.login_id == 0:
            raise RuntimeError("Not logged in.")
            
        f_struct = file_info.get("recordfile_info_struct")
        if not f_struct:
            raise ValueError("Invalid file_info dictionary. Missing C structure.")
            
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
                
        print(f"Downloading file to {output_path}...")
        dl_handle = self.sdk.CLIENT_DownloadByRecordFile(
            self.login_id, 
            byref(f_struct), 
            output_path.encode('utf-8'), 
            None, 
            None
        )
        
        if dl_handle == 0:
            last_err = self.sdk.CLIENT_GetLastError()
            raise RuntimeError(f"Download failed to start. SDK Error: {last_err}")

        self._wait_for_download(dl_handle, progress_callback)

    def download_by_time(self, channel, start_time_str, end_time_str, output_path, record_type=0, progress_callback=None):
        """
        Downloads recordings within a specific timeframe directly.
        """
        if self.login_id == 0:
            raise RuntimeError("Not logged in.")

        tm_start = NET_TIME.from_string(start_time_str)
        tm_end = NET_TIME.from_string(end_time_str)

        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass

        print(f"Downloading Channel {channel} ({start_time_str} to {end_time_str}) to {output_path}...")
        dl_handle = self.sdk.CLIENT_DownloadByTime(
            self.login_id, 
            channel, 
            record_type, 
            byref(tm_start), 
            byref(tm_end), 
            output_path.encode('utf-8'), 
            None, 
            None
        )
        
        if dl_handle == 0:
            last_err = self.sdk.CLIENT_GetLastError()
            raise RuntimeError(f"Download by time failed to start. SDK Error: {last_err}")

        self._wait_for_download(dl_handle, progress_callback)

    def _wait_for_download(self, dl_handle, progress_callback=None):
        total_size = c_int(0)
        dl_size = c_int(0)
        last_pct = -1.0
        
        last_dl_size = -1
        last_change_time = time.time()
        timeout_seconds = 60 # 60 seconds timeout if no progress
        
        try:
            while True:
                res_pos = self.sdk.CLIENT_GetDownloadPos(dl_handle, byref(total_size), byref(dl_size))
                if not res_pos:
                    print("Failed to get download position.")
                    break
                    
                t_sz = total_size.value
                d_sz = dl_size.value
                
                if t_sz == -1:
                    print("\nDownload completed or stopped by error.")
                    break
                    
                if t_sz > 0:
                    # Check for progress timeout
                    if d_sz > last_dl_size:
                        last_dl_size = d_sz
                        last_change_time = time.time()
                    elif time.time() - last_change_time > timeout_seconds:
                        raise TimeoutError(f"Download timed out: No data received for {timeout_seconds} seconds.")
                        
                    pct = (d_sz / t_sz) * 100
                    if progress_callback:
                        progress_callback(d_sz, t_sz, pct)
                    else:
                        if pct - last_pct >= 5.0 or d_sz >= t_sz:
                            print(f"Progress: {d_sz}/{t_sz} KB ({pct:.2f}%)")
                            last_pct = pct
                            
                    if d_sz >= t_sz:
                        print("Download finished.")
                        break
                else:
                    # Prevent infinite buffering state if DVR doesn't reply
                    if time.time() - last_change_time > timeout_seconds:
                        raise TimeoutError(f"Buffering timed out: Failed to start downloading within {timeout_seconds} seconds.")
                    print("Connecting / buffering stream...")
                    
                time.sleep(1.0)
        finally:
            self.sdk.CLIENT_StopDownload(dl_handle)


    def close(self):
        self.logout()
        if self.sdk:
            self.sdk.CLIENT_Cleanup()
            self.sdk = None
            print("SDK Cleaned up.")
