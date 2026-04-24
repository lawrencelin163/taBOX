#!/usr/bin/env python3
"""
Active_Bot.py
複製 openclaw 配置檔案到特定的目標目錄，並啟動對應的 service
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


def get_active_number():
    """
    獲取 active number (NNN)
    可以從環境變數、配置檔案或命令行參數獲取
    """
    # 優先順序：命令行參數 > 環境變數 > 默認值
    if len(sys.argv) > 1:
        return sys.argv[1]
    
    if "OPENCLAW_ACTIVE_NO" in os.environ:
        return os.environ["OPENCLAW_ACTIVE_NO"]
    
    # 如果沒有提供，提示用戶
    print("Error: Active number not provided")
    print("Usage: python3 Active_Bot.py <active_number>")
    print("Or set environment variable: OPENCLAW_ACTIVE_NO=<number>")
    sys.exit(1)


def create_directory(path):
    """建立目錄（如果不存在）"""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        print(f"✓ Directory created: {path}")
        return True
    except Exception as e:
        print(f"✗ Error creating directory {path}: {e}")
        return False


def copy_file(source, destination):
    """複製檔案"""
    try:
        # 確保目標目錄存在
        dest_dir = os.path.dirname(destination)
        create_directory(dest_dir)
        
        # 複製檔案
        shutil.copy2(source, destination)
        print(f"✓ Copied: {source} → {destination}")
        return True
    except FileNotFoundError:
        print(f"✗ Source file not found: {source}")
        return False
    except Exception as e:
        print(f"✗ Error copying {source} to {destination}: {e}")
        return False


def enable_service(service_name):
    """啟用 systemd service"""
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "enable", service_name],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"✓ Service enabled: {service_name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Error enabling service {service_name}: {e.stderr}")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def restart_service(service_name):
    """重啟 systemd service，確保新配置生效"""
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "restart", service_name],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"✓ Service restarted: {service_name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Error restarting service {service_name}: {e.stderr}")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def main():
    """主程序"""
    print("=" * 60)
    print("Active_Bot - Openclaw Configuration Activator")
    print("=" * 60)
    
    # 獲取 active number
    active_no = get_active_number()
    print(f"\nActive Number: {active_no}")
    
    # 定義路徑
    base_source = "/home/yf/.openclaw"
    base_target = f"/home/yf/.openclaw-{active_no}"
    
    print(f"Source: {base_source}")
    print(f"Target: {base_target}\n")
    
    # 複製 4 個檔案
    files_to_copy = [
        {
            "source": f"{base_source}/openclaw.json",
            "target": f"{base_target}/openclaw.json"
        },
        {
            "source": f"{base_source}/agents/main/agent/auth-profiles.json",
            "target": f"{base_target}/agents/main/agent/auth-profiles.json"
        },
        {
            "source": f"{base_source}/agents/main/agent/auth-state.json",
            "target": f"{base_target}/agents/main/agent/auth-state.json"
        },
        {
            "source": f"{base_source}/agents/main/agent/models.json",
            "target": f"{base_target}/agents/main/agent/models.json"
        }
    ]
    
    print("Copying configuration files:")
    print("-" * 60)
    copy_success_count = 0
    for file_info in files_to_copy:
        if copy_file(file_info["source"], file_info["target"]):
            copy_success_count += 1
    
    print(f"\nCopied {copy_success_count}/{len(files_to_copy)} files\n")
    
    # 啟用並重啟 service
    service_name = f"openclaw-gateway-{active_no}.service"
    print("Enabling and restarting service:")
    print("-" * 60)
    
    if enable_service(service_name) and restart_service(service_name):
        print("\n" + "=" * 60)
        print("✓ All tasks completed successfully!")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("✗ Some tasks failed. Please check the errors above.")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
