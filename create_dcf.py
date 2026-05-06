import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "DCF Valuation"

# 样式定义
header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
header_font = Font(bold=True, color="FFFFFF", size=12)
blue_fill = PatternFill(start_color="D6DCE4", end_color="D6DCE4", fill_type="solid")
input_fill = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")
center_align = Alignment(horizontal="center", vertical="center")
thin_border = Border(
    left=Side(style='thin'), right=Side(style='thin'),
    top=Side(style='thin'), bottom=Side(style='thin')
)

# 标题
ws.merge_cells('A1:H1')
ws['A1'] = "中国石油 (601857) DCF 估值模型"
ws['A1'].font = Font(bold=True, size=14)
ws['A1'].alignment = center_align

# === 第一部分：关键输入 ===
ws['A3'] = "关键输入"
ws['A3'].font = header_font
ws['A3'].fill = header_fill
ws.merge_cells('A3:B3')

ws['A4'] = "当前股价"
ws['B4'] = 8.5
ws['B4'].fill = input_fill

ws['A5'] = "股数（亿股）"
ws['B5'] = 183
ws['B5'].fill = input_fill

ws['A6'] = "WACC"
ws['B6'] = 0.10
ws['B6'].fill = input_fill

ws['A7'] = "永续增长率"
ws['B7'] = 0.02
ws['B7'].fill = input_fill

# === 第二部分：收入预测 ===
ws['A9'] = "收入预测（亿元）"
ws['A9'].font = header_font
ws['A9'].fill = header_fill
ws.merge_cells('A9:F9')

ws['A10'] = "年份"
ws['B10'] = "2024E"
ws['C10'] = "2025E"
ws['D10'] = "2026E"
ws['E10'] = "2027E"
ws['F10'] = "2028E"

ws['A11'] = "收入"
ws['B11'] = 28800
ws['C11'] = "=B11*1.03"
ws['D11'] = "=C11*1.03"
ws['E11'] = "=D11*1.03"
ws['F11'] = "=E11*1.03"

ws['A12'] = "增长率"
ws['B12'] = "3%"
ws['C12'] = "3%"
ws['D12'] = "3%"
ws['E12'] = "3%"
ws['F12'] = "3%"

# === 第三部分：净利润 ===
ws['A14'] = "净利润预测（亿元）"
ws['A14'].font = header_font
ws['A14'].fill = header_fill
ws.merge_cells('A14:F14')

ws['A15'] = "净利润率"
ws['B15'] = 0.06

ws['A16'] = "净利润"
ws['B16'] = "=B11*B15"
ws['C16'] = "=C11*B15"
ws['D16'] = "=D11*B15"
ws['E16'] = "=E11*B15"
ws['F16'] = "=F11*B15"

# === 第四部分：自由现金流 ===
ws['A18'] = "自由现金流（亿元）"
ws['A18'].font = header_font
ws['A18'].fill = header_fill
ws.merge_cells('A18:F18')

ws['A19'] = "FCF/净利润比"
ws['B19'] = 0.80

ws['A20'] = "自由现金流"
ws['B20'] = "=B16*B19"
ws['C20'] = "=C16*B19"
ws['D20'] = "=D16*B19"
ws['E20'] = "=E16*B19"
ws['F20'] = "=F16*B19"

# === 第五部分：折现 ===
ws['A22'] = "折现计算"
ws['A22'].font = header_font
ws['A22'].fill = header_fill
ws.merge_cells('A22:F22')

ws['A23'] = "折现因子"
ws['B23'] = "=1/(1+$B$6)^1"
ws['C23'] = "=1/(1+$B$6)^2"
ws['D23'] = "=1/(1+$B$6)^3"
ws['E23'] = "=1/(1+$B$6)^4"
ws['F23'] = "=1/(1+$B$6)^5"

ws['A24'] = "PV"
ws['B24'] = "=B20*B23"
ws['C24'] = "=C20*C23"
ws['D24'] = "=D20*D23"
ws['E24'] = "=E20*E23"
ws['F24'] = "=F20*F23"

ws['A25'] = "预测期现值合计"
ws['B25'] = "=SUM(B24:F24)"

# === 第六部分：终值 ===
ws['A27'] = "终值计算"
ws['A27'].font = header_font
ws['A27'].fill = header_fill
ws.merge_cells('A27:C27')

ws['A28'] = "2028年FCF"
ws['B28'] = "=F20"

ws['A29'] = "终值"
ws['B29'] = "=B28*(1+$B$7)/($B$6-$B$7)"

ws['A30'] = "终值现值"
ws['B30'] = "=B29*F23"

# === 第七部分：估值结果 ===
ws['A32'] = "估值结果"
ws['A32'].font = header_font
ws['A32'].fill = header_fill
ws.merge_cells('A32:C32')

ws['A33'] = "企业价值(EV)"
ws['B33'] = "=B25+B30"

ws['A34'] = "减：净债务"
ws['B34'] = 3000

ws['A35'] = "股权价值"
ws['B35'] = "=B33-B34"

ws['A36'] = "股数（亿股）"
ws['B36'] = "=B5"

ws['A37'] = "每股价值"
ws['B37'] = "=B35/B36"

ws['A39'] = "当前股价"
ws['B39'] = "=B4"

ws['A40'] = "上行空间"
ws['B40'] = "=B37/B39-1"

# 调整列宽
ws.column_dimensions['A'].width = 20
for col in ['B', 'C', 'D', 'E', 'F']:
    ws.column_dimensions[col].width = 12

wb.save('C:/Users/xrt85/Desktop/3月22日课程资料/cufel_arena/中国石油DCF.xlsx')
print("Excel文件已创建: 中国石油DCF.xlsx")