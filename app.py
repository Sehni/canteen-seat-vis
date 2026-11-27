import streamlit as st
import matplotlib.pyplot as plt
from PIL import Image
import numpy as np
import re

# ==========================================
# 1. 数据解析
# ==========================================
@st.cache_data
def parse_data(filepath):
    """专门解析带有时间戳和空行的数据文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    right_lines = []
    left_blocks = []
    current_block = []
    current_time = ""
    
    for line in lines:
        line = line.strip()
        if not line or "特定区域" in line:
            continue
        
        if ':' in line:  # 遇到时间戳，比如 12:12
            if current_block:
                left_blocks.append((current_time, current_block))
                current_block = []
            current_time = line
        else:
            if current_time:
                current_block.append(line)
            else:
                right_lines.append(line)
                
    if current_block:
        left_blocks.append((current_time, current_block))
        
    def extract_nums(line_list):
        """把行里的 4位数字 拆成一个个独立的整数"""
        result = []
        for line in line_list:
            parts = line.split()
            for part in parts:
                result.extend([int(c) for c in part])
        return result

    # 解析右侧数据（每2行对应一个时间点的左右2列）
    right_data = [extract_nums([line]) for line in right_lines]
    
    # 解析左侧数据
    left_data = []
    times = []
    for time_label, block in left_blocks:
        times.append(time_label)
        for line in block:
            left_data.append(extract_nums([line]))
            
    # 组装 5 个时间点
    time_steps = []
    for t in range(5):
        time_steps.append({
            'time_label': times[t] if t < len(times) else f"T+{t*5}",
            'right_in':  right_data[t*2] if t*2 < len(right_data) else [0]*36,
            'right_out': right_data[t*2+1] if t*2+1 < len(right_data) else [0]*36,
            'left_in':   left_data[t*2] if t*2 < len(left_data) else [0]*36,
            'left_out':  left_data[t*2+1] if t*2+1 < len(left_data) else [0]*36
        })
    return time_steps

# ==========================================
# 2. 图像渲染类
# ==========================================
class Unit:
    def __init__(self, x, y, assets, ax):
        self.x, self.y = x, y
        self.ax = ax
        self.desk_w = 3.0
        self.seat_w = 1.2
        self.offset = self.desk_w / 2 + self.seat_w / 2 + 0.2
        
        self.load_desk()
        self.load_seat()
        
    def load_desk(self):
        extent = (self.x - self.desk_w/2, self.x + self.desk_w/2, 
                  self.y - self.desk_w/2, self.y + self.desk_w/2)
        self.desk = self.ax.imshow(self.assets['desk'], extent=extent, zorder=0, aspect='auto')
        
    def load_seat(self):
        self.seat = []
        # 4个座位方向: 左上, 左下, 右下, 右上
        directions = [(-1, 1), (-1, -1), (1, -1), (1, 1)]
        
        for dx, dy in directions:
            sx = self.x + dx * self.offset
            sy = self.y + dy * self.offset
            extent = (sx - self.seat_w/2, sx + self.seat_w/2, 
                      sy - self.seat_w/2, sy + self.seat_w/2)
            
            blank = self.ax.imshow(self.assets['blank'], extent=extent, zorder=10, aspect='auto')
            person = self.ax.imshow(self.assets['person'], extent=extent, zorder=10, aspect='auto')
            stuff = self.ax.imshow(self.assets['stuff'], extent=extent, zorder=10, aspect='auto')
            
            self.seat.append((blank, person, stuff))
            
        for i in range(4):
            for j in range(3):
                self.seat[i][j].set_visible(False)

    def shift(self, place, state):
        for i in range(3):
            self.seat[place][i].set_visible(i == state)

class Editor:
    def __init__(self, assets):
        self.fig, self.ax = plt.subplots(figsize=(10, 10), dpi=100)
        # 设置画布范围，容纳 4 列桌子
        self.ax.set_xlim(-10, 10)
        self.ax.set_ylim(0, 22)
        self.ax.set_aspect('equal')
        self.ax.axis('off')
        
        self.assets = assets
        
        # 4列对应的x坐标: 左外、左内、过道、右内、右外
        self.cols = {
            'left_out': -8, 
            'left_in': -4,
            'right_in': 4,
            'right_out': 8
        }
        self.units = {k: [] for k in self.cols}
        
        # 生成 4×9 = 36 个桌子
        for i in range(9):
            y = 18 - i * 2  # 从下往上或者从上往下
            for key, x in self.cols.items():
                self.units[key].append(Unit(x, y, self.assets, self.ax))
                
        # 画布中心线（过道指示）
        self.ax.plot([0, 0], [0, 20], color='gray', linestyle='--', alpha=0.3, zorder=-1)

    def update_state(self, step_data):
        # 将数据映射到 4 列
        mapping = {
            'left_out':  step_data['left_out'],
            'left_in':   step_data['left_in'],
            'right_in':  step_data['right_in'],
            'right_out': step_data['right_out']
        }
        
        for col_key, data_array in mapping.items():
            units_list = self.units[col_key]
            for i, unit in enumerate(units_list):
                # 每个桌子 4 个座位
                seat_states = data_array[i*4 : (i+1)*4]
                for seat_idx in range(4):
                    state = seat_states[seat_idx]
                    unit.shift(seat_idx, state)

# ==========================================
# 3. 缓存图片加载
# ==========================================
@st.cache_resource
def load_images():
    def load_image(path):
        try:
            with Image.open(path) as im:
                im = im.convert("RGBA")
                im.thumbnail((128, 128), Image.Resampling.LANCZOS) 
                return np.asarray(im, dtype=np.float32) / 255.0
        except FileNotFoundError:
            # 如果找不到图片，生成一个纯色占位图，防止网页崩溃
            color = [1,0,0,1] if "有人" in path else ([1,1,0,1] if "占座" in path else [0.8,0.8,0.8,1])
            return np.ones((64, 64, 4), dtype=np.float32) * color

    return {
        'desk': load_image("assets/空座位.png"), 
        'blank': load_image("assets/空座位.png"),
        'stuff': load_image("assets/占座.png"),
        'person': load_image("assets/有人.png")
    }

# ==========================================
# 4. Streamlit 页面
# ==========================================
def main():
    st.set_page_config(page_title="食堂座位状态监控", layout="wide")
    st.title("🍽️ 食堂座位状态监控 (12:12 - 12:32)")
    
    try:
        time_steps = parse_data("data1-11.25.txt")
    except FileNotFoundError:
        st.error("找不到数据文件！请确保 `data1-11.25.txt` 和代码在同一目录下。")
        return

    labels = [t['time_label'] for t in time_steps]
    
    # 侧边栏
    st.sidebar.header("控制面板")
    selected_idx = st.sidebar.selectbox("选择时间点", range(len(time_steps)), format_func=lambda x: labels[x])
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 图例说明")
    st.sidebar.markdown("- 灰色/空位：0（空）")
    st.sidebar.markdown("- 红色/有人：1（有人）")
    st.sidebar.markdown("- 黄色/物品：2（有物品）")
    
    current_step = time_steps[selected_idx]
    
    # 缓存图片
    assets = load_images()
    
    # 生成画布
    editor = Editor(assets)
    editor.update_state(current_step)
    
    # 显示图像
    col1, col2, col3 = st.columns([1, 4, 1])
    with col2:
        st.pyplot(editor.fig)
    
if __name__ == "__main__":
    main()
