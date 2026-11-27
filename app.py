import streamlit as st
import matplotlib.pyplot as plt
from PIL import Image
import numpy as np
import os
import time

# ==========================================
# 1. 数据解析
# ==========================================
@st.cache_data
def parse_data(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    right_lines, left_blocks, current_block, current_time = [], [], [], ""
    
    for line in lines:
        line = line.strip()
        if not line or "特定区域" in line:
            continue
        
        if ':' in line:
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
        result = []
        for line in line_list:
            for part in line.split():
                result.extend([int(c) for c in part])
        return result

    right_data = [extract_nums([line]) for line in right_lines]
    left_data, times = [], []
    
    for time_label, block in left_blocks:
        times.append(time_label)
        for line in block:
            left_data.append(extract_nums([line]))
            
    time_steps = []
    for t in range(5):
        time_steps.append({
            'time_label': times[t] if t < len(times) else f"T+{t*5}",
            'right_1': right_data[t*2] if t*2 < len(right_data) else [0]*36,
            'right_2': right_data[t*2+1] if t*2+1 < len(right_data) else [0]*36,
            'left_1':  left_data[t*2] if t*2 < len(left_data) else [0]*36,
            'left_2':  left_data[t*2+1] if t*2+1 < len(left_data) else [0]*36
        })
    return time_steps

# ==========================================
# 2. 图像渲染类 (精准匹配物理遍历顺序)
# ==========================================
class Unit:
    def __init__(self, x, y, assets, ax):
        self.x, self.y = x, y
        self.ax = ax
        self.assets = assets
        self.desk_w = 2.2      
        self.seat_w = 0.8      
        self.load_desk()
        self.load_seat()
        
    def load_desk(self):
        extent = (self.x - self.desk_w/2, self.x + self.desk_w/2, 
                  self.y - self.desk_w/2, self.y + self.desk_w/2)
        self.desk = self.ax.imshow(self.assets['desk'], extent=extent, zorder=0, aspect='auto')
        
    def load_seat(self):
        self.seat = []
        offset = self.desk_w / 4.0  
        # 座位顺序：左上, 左下, 右下, 右上 (严格按照你最初的数据采集顺序)
        directions = [(-1, 1), (-1, -1), (1, -1), (1, 1)] 
        
        for dx, dy in directions:
            sx = self.x + dx * offset
            sy = self.y + dy * offset
            extent = (sx - self.seat_w/2, sx + self.seat_w/2, 
                      sy - self.seat_w/2, sy + self.seat_w/2)
            
            blank = self.ax.imshow(self.assets['blank'], extent=extent, zorder=10, aspect='auto')
            person = self.ax.imshow(self.assets['person'], extent=extent, zorder=10, aspect='auto')
            stuff = self.ax.imshow(self.assets['stuff'], extent=extent, zorder=10, aspect='auto')
            
            self.seat.append((blank, person, stuff))
            blank.set_visible(False)
            person.set_visible(False)
            stuff.set_visible(False)

    def shift(self, place, state):
        for i in range(3):
            self.seat[place][i].set_visible(i == state)

class Editor:
    def __init__(self, assets):
        self.fig, self.ax = plt.subplots(figsize=(15, 5), dpi=100)
        self.fig.patch.set_alpha(0.0)
        self.ax.patch.set_alpha(0.0)
        
        self.ax.set_xlim(-32, 32)
        self.ax.set_ylim(-3, 11)
        self.ax.set_aspect('equal')
        self.ax.axis('off')
        
        self.assets = assets
        self.ax.fill_between([-31, -5], -2.5, 10.5, color='#f0f2f6', zorder=-5)
        self.ax.fill_between([5, 31], -2.5, 10.5, color='#f0f2f6', zorder=-5)

        self.units = {'left_1': [], 'left_2': [], 'right_1': [], 'right_2': []}
        self.create_layout()

    def create_layout(self):
        # 物理坐标排布
        x_left = np.linspace(-28, -8, 9)  # 左边从墙到中间 (-28 -> -8)
        x_right = np.linspace(8, 28, 9)   # 右边从中间到墙 (8 -> 28)
        
        # ================= 左区 =================
        # 数据第一行 left_1：从中间下面开始向左走 -> 对应 x_left 倒序 (-8 -> -28)
        for x in x_left[::-1]: 
            self.units['left_1'].append(Unit(x=x, y=1, assets=self.assets, ax=self.ax))
            
        # 数据第二行 left_2：绕到上面一排回到中间 -> 对应 x_left 正序 (-28 -> -8)
        for x in x_left: 
            self.units['left_2'].append(Unit(x=x, y=7, assets=self.assets, ax=self.ax))
            
        # ================= 右区 =================
        # 数据第一行 right_1：从中间下面开始向右走 -> 对应 x_right 正序 (8 -> 28)
        for x in x_right: 
            self.units['right_1'].append(Unit(x=x, y=1, assets=self.assets, ax=self.ax))
            
        # 数据第二行 right_2：绕到上面一排回到中间 -> 对应 x_right 倒序 (28 -> 8)
        for x in x_right[::-1]: 
            self.units['right_2'].append(Unit(x=x, y=7, assets=self.assets, ax=self.ax))

    def update_state(self, step_data):
        # 现在 units 里面保存的顺序，已经完全和 step_data 的数组顺序一一对应
        mapping = {
            'left_1':  step_data['left_1'], 
            'left_2':  step_data['left_2'], 
            'right_1': step_data['right_1'], 
            'right_2': step_data['right_2']
        }
        
        for key, data_array in mapping.items():
            units_list = self.units[key]
            for i, unit in enumerate(units_list):
                seat_states = data_array[i*4 : (i+1)*4]
                for seat_idx in range(4):
                    unit.shift(seat_idx, seat_states[seat_idx])

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
            color = [0.9, 0.2, 0.2, 1] if "有人" in path else ([0.9, 0.8, 0.2, 1] if "占座" in path else [0.8, 0.8, 0.8, 1])
            return np.ones((64, 64, 4), dtype=np.float32) * color

    return {
        'desk': load_image("assets/空座位.png"), 
        'blank': load_image("assets/空座位.png"),
        'stuff': load_image("assets/占座.png"),
        'person': load_image("assets/有人.png")
    }

# ==========================================
# 4. Streamlit 页面与播放逻辑
# ==========================================
def main():
    st.set_page_config(page_title="食堂座位状态监控", layout="wide")
    st.title("🍽️ 食堂座位状态监控")
    
    file_path = os.path.join("data", "data1-11.25.txt")
    
    try:
        time_steps = parse_data(file_path)
    except Exception as e:
        st.error(f"数据读取失败：{e}。")
        return

    if 'time_idx' not in st.session_state:
        st.session_state.time_idx = 0
    if 'is_playing' not in st.session_state:
        st.session_state.is_playing = False

    st.sidebar.header("控制面板")
    
    play_btn_text = "⏸️ 暂停播放" if st.session_state.is_playing else "▶️ 开始播放"
    st.sidebar.button(play_btn_text, on_click=lambda: st.session_state.update(is_playing=not st.session_state.is_playing), use_container_width=True)
    
    current_val = st.sidebar.slider(
        "拖动查看时间点", 
        min_value=0, 
        max_value=len(time_steps)-1, 
        value=st.session_state.time_idx, 
        format="第 %d 个时间点"
    )
    
    if current_val != st.session_state.time_idx:
        st.session_state.time_idx = current_val
        st.session_state.is_playing = False
        st.rerun() 
        
    current_step = time_steps[st.session_state.time_idx]
    st.sidebar.info(f"当前时间：**{current_step['time_label']}**")
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 图例说明")
    st.sidebar.markdown("- ⚪ 空位：0（空）")
    st.sidebar.markdown("- 🔴 有人：1（有人）")
    st.sidebar.markdown("- 🟡 物品：2（有物品）")
    
    assets = load_images()
    editor = Editor(assets)
    editor.update_state(current_step)
    st.pyplot(editor.fig)
    
    if st.session_state.is_playing:
        if st.session_state.time_idx < len(time_steps) - 1:
            time.sleep(1.5) 
            st.session_state.time_idx += 1
            st.rerun()       
        else:
            st.session_state.is_playing = False
            st.rerun()

if __name__ == "__main__":
    main()
