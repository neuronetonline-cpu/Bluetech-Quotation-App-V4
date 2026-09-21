import os, sqlite3, subprocess, sys
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

APP_DIR = os.path.join(os.path.expanduser("~"), "BluetechQuotationApp")
os.makedirs(APP_DIR, exist_ok=True)
DB = os.path.join(APP_DIR, "quotations.db")
PDF_DIR = os.path.join(APP_DIR, "Quotations")
os.makedirs(PDF_DIR, exist_ok=True)

DEFAULT_PRODUCTS = [
    "MOTHER BOARD", "PROCESSOR", "CPU FAN", "RAMS", "PSU", "CASING", "CASING FANS",
    "SSD", "HDD", "VGA (used -03m)", "MONITOR (used-03m)", "ALL CABLES",
    "MOUSE", "KEYBOARD", "SPEAKER", "WIFI ADAPTER"
]

BLUE = "#075EAA"
DARK_BLUE = "#12345B"
LIGHT_BLUE = "#EAF4FF"
LIGHT_GREEN = "#ECF9F0"
GREEN = "#159447"
GREY = "#667085"


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def register_fonts():
    font_path = resource_path("Deadly Advance.ttf")
    if os.path.exists(font_path):
        try:
            pdfmetrics.registerFont(TTFont("DeadlyAdvance", font_path))
            return True
        except Exception:
            pass
    return False


DEADLY_ADVANCE_AVAILABLE = register_fonts()


def db():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS quotations(
        id INTEGER PRIMARY KEY AUTOINCREMENT, qno TEXT, customer TEXT, phone TEXT,
        date TEXT, profit REAL DEFAULT 0, warranty90 REAL DEFAULT 0,
        warranty180 REAL DEFAULT 0, weight REAL DEFAULT 0, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, quotation_id INTEGER,
        product TEXT, description TEXT, qty REAL, cost REAL)""")
    # Upgrade databases created by the first version.
    cols = {r[1] for r in c.execute("PRAGMA table_info(quotations)").fetchall()}
    if "warranty90" not in cols:
        c.execute("ALTER TABLE quotations ADD COLUMN warranty90 REAL DEFAULT 0")
    if "warranty180" not in cols:
        c.execute("ALTER TABLE quotations ADD COLUMN warranty180 REAL DEFAULT 0")
    item_cols = {r[1] for r in c.execute("PRAGMA table_info(items)").fetchall()}
    if "cost" not in item_cols:
        c.execute("ALTER TABLE items ADD COLUMN cost REAL DEFAULT 0")
    c.commit()
    return c


def next_qno():
    c = db()
    n = c.execute("SELECT COUNT(*) FROM quotations").fetchone()[0] + 1
    c.close()
    return f"QT-{datetime.now():%Y%m%d}-{n:04d}"


def money(v):
    return f"LKR {v:,.2f}"


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Bluetech Computers - Desktop Quotation")
        self.root.geometry("1320x800")
        self.root.minsize(1100, 700)
        self.rows = []
        self.editing_id = None
        self.build()

    def build(self):
        top = ttk.Frame(self.root, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="BLUETECH COMPUTERS", font=("Segoe UI", 20, "bold")).pack(side="left")
        ttk.Button(top, text="Quotation History", command=self.history).pack(side="right", padx=5)
        ttk.Button(top, text="New Quotation", command=self.new_quote).pack(side="right")

        info = ttk.LabelFrame(self.root, text="Customer / Quotation", padding=10)
        info.pack(fill="x", padx=12, pady=5)
        self.qno = tk.StringVar(value=next_qno())
        self.customer = tk.StringVar()
        self.phone = tk.StringVar()
        self.qdate = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        fields = [("Quotation No.", self.qno), ("Customer Name", self.customer),
                  ("WhatsApp / Phone", self.phone), ("Date", self.qdate)]
        for i, (lab, var) in enumerate(fields):
            ttk.Label(info, text=lab).grid(row=0, column=i * 2, sticky="w", padx=5)
            ttk.Entry(info, textvariable=var, width=25).grid(row=0, column=i * 2 + 1, sticky="ew", padx=5)
        for i in range(8):
            info.columnconfigure(i, weight=1)

        box = ttk.LabelFrame(self.root, text="Quotation Items (Cost and Profit are INTERNAL ONLY)", padding=8)
        box.pack(fill="both", expand=True, padx=12, pady=5)

        heads = ["PRODUCT", "PRODUCT DESCRIPTION", "QTY", "COST (INTERNAL)", "REMOVE"]
        for j, h in enumerate(heads):
            ttk.Label(box, text=h, font=("Segoe UI", 9, "bold")).grid(row=0, column=j, padx=3, pady=4, sticky="ew")
        self.table = ttk.Frame(box)
        self.table.grid(row=1, column=0, columnspan=5, sticky="nsew")
        box.rowconfigure(1, weight=1)
        for j, w in enumerate([23, 42, 10, 20, 10]):
            box.columnconfigure(j, weight=1, minsize=w * 8)

        self.rows = []
        for p in DEFAULT_PRODUCTS:
            self.add_row(p, silent=True)

        controls = ttk.Frame(self.root, padding=8)
        controls.pack(fill="x", padx=12)
        ttk.Button(controls, text="+ ADD PRODUCT / ROW", command=lambda: self.add_row("")).pack(side="left")

        self.total_cost = tk.StringVar(value="LKR 0.00")
        self.profit = tk.StringVar(value="0")
        self.final90 = tk.StringVar(value="LKR 0.00")
        self.final180 = tk.StringVar(value="LKR 0.00")
        self.weight = tk.StringVar(value="0")

        calc = ttk.LabelFrame(self.root, text="Internal Calculation", padding=10)
        calc.pack(fill="x", padx=12, pady=5)
        labels = [
            ("Total Cost", self.total_cost),
            ("Requested Profit", self.profit),
            ("90 Days Final Price", self.final90),
            ("180 Days Final Price (+35%)", self.final180),
            ("Weight (KG)", self.weight),
        ]
        for i, (lab, var) in enumerate(labels):
            ttk.Label(calc, text=lab).grid(row=0, column=i, padx=5)
            e = ttk.Entry(calc, textvariable=var, width=22)
            e.grid(row=1, column=i, padx=5)
            if lab in ("Requested Profit", "Weight (KG)"):
                e.bind("<KeyRelease>", lambda e: self.recalc())
        ttk.Button(calc, text="CALCULATE", command=self.recalc).grid(row=1, column=5, padx=8)

        actions = ttk.Frame(self.root, padding=10)
        actions.pack(fill="x", padx=12)
        ttk.Button(actions, text="PREVIEW / SAVE PDF", command=self.save_pdf).pack(side="right", padx=5)
        ttk.Button(actions, text="SAVE QUOTATION", command=self.save_quote).pack(side="right", padx=5)
        ttk.Button(actions, text="CLEAR", command=self.new_quote).pack(side="right", padx=5)
        self.recalc()

    def add_row(self, product="", silent=False):
        r = len(self.rows)
        p = tk.StringVar(value=product)
        d = tk.StringVar()
        q = tk.StringVar(value="1")
        c = tk.StringVar(value="0")
        widgets = []
        for j, var in enumerate([p, d, q, c]):
            e = ttk.Entry(self.table, textvariable=var)
            e.grid(row=r, column=j, padx=2, pady=2, sticky="ew")
            widgets.append(e)
            e.bind("<KeyRelease>", lambda e: self.recalc())
        btn = ttk.Button(self.table, text="X", width=5, command=lambda rr=r: self.remove_row(rr))
        btn.grid(row=r, column=4, padx=2)
        self.rows.append((p, d, q, c, widgets, btn))
        if not silent:
            self.recalc()

    def remove_row(self, idx):
        if idx >= len(self.rows):
            return
        for w in self.rows[idx][4]:
            w.destroy()
        self.rows[idx][5].destroy()
        self.rows.pop(idx)
        for r, row in enumerate(self.rows):
            for j, w in enumerate(row[4]):
                w.grid_configure(row=r, column=j)
            row[5].grid_configure(row=r, column=4)
        self.recalc()

    def num(self, x):
        try:
            return float(str(x).replace(",", "").replace("LKR", "").strip() or 0)
        except Exception:
            return 0

    def recalc(self):
        cost = 0
        for p, d, q, c, *_ in self.rows:
            qty = self.num(q.get())
            cost += qty * self.num(c.get())
        profit = self.num(self.profit.get())
        final90 = cost + profit
        final180 = final90 * 1.35
        self.total_cost.set(money(cost))
        self.final90.set(money(final90))
        self.final180.set(money(final180))

    def collect_items(self):
        out = []
        for p, d, q, c, *_ in self.rows:
            if p.get().strip() and self.num(q.get()) > 0:
                out.append((p.get().strip(), d.get().strip(), self.num(q.get()), self.num(c.get())))
        return out

    def save_quote(self):
        items = self.collect_items()
        if not self.customer.get().strip():
            messagebox.showwarning("Customer", "Enter customer name.")
            return
        self.recalc()
        c = db()
        values = (self.qno.get(), self.customer.get(), self.phone.get(), self.qdate.get(),
                  self.num(self.profit.get()), self.num(self.final90.get()), self.num(self.final180.get()),
                  self.num(self.weight.get()), datetime.now().isoformat())
        if self.editing_id is not None:
            c.execute("""UPDATE quotations SET qno=?,customer=?,phone=?,date=?,profit=?,warranty90=?,warranty180=?,weight=?,created_at=? WHERE id=?""",
                      values + (self.editing_id,))
            c.execute("DELETE FROM items WHERE quotation_id=?", (self.editing_id,))
            qid = self.editing_id
            action = "updated"
        else:
            c.execute("""INSERT INTO quotations(qno,customer,phone,date,profit,warranty90,warranty180,weight,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?)""", values)
            qid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
            action = "saved"
        c.executemany("INSERT INTO items(quotation_id,product,description,qty,cost) VALUES(?,?,?,?,?)",
                      [(qid, *x) for x in items])
        c.commit()
        c.close()
        self.editing_id = qid
        messagebox.showinfo("Saved", f"Quotation {self.qno.get()} {action}.")
        return qid

    def save_pdf(self):
        self.recalc()
        items = self.collect_items()
        if not self.customer.get().strip():
            messagebox.showwarning("Customer", "Enter customer name.")
            return

        filename = os.path.join(PDF_DIR, f"{self.qno.get()}.pdf")
        styles = getSampleStyleSheet()
        title = ParagraphStyle("title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24,
                               leading=27, textColor=colors.HexColor(DARK_BLUE), alignment=TA_LEFT, spaceAfter=2)
        logo_font = "DeadlyAdvance" if DEADLY_ADVANCE_AVAILABLE else "Helvetica-Bold"
        subtitle = ParagraphStyle("subtitle", parent=styles["BodyText"], fontSize=8.5, leading=10,
                                  textColor=colors.HexColor(DARK_BLUE), alignment=TA_LEFT)
        small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=7.5, leading=9.5, textColor=colors.HexColor(GREY))
        normal = ParagraphStyle("normal", parent=styles["BodyText"], fontSize=8.5, leading=11, textColor=colors.HexColor(DARK_BLUE))
        info_style = ParagraphStyle("info", parent=styles["BodyText"], fontSize=8.5, leading=12, textColor=colors.HexColor(DARK_BLUE))
        price_style = ParagraphStyle("price", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=14,
                                     leading=16, textColor=colors.white, alignment=TA_CENTER)
        warranty_style = ParagraphStyle("warranty", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=10,
                                        leading=12, textColor=colors.HexColor(DARK_BLUE), alignment=TA_LEFT)

        doc = SimpleDocTemplate(filename, pagesize=A4, rightMargin=12 * mm, leftMargin=12 * mm,
                                topMargin=10 * mm, bottomMargin=10 * mm)
        story = []

        logo_style = ParagraphStyle("logo", parent=title, fontName=logo_font, fontSize=24, leading=25,
                                    textColor=colors.HexColor(DARK_BLUE), alignment=TA_LEFT)
        header_left = [Paragraph("BLUETECH COMPUTERS", logo_style),
                       Paragraph("Computer Sales | Repairs | Upgrades", subtitle)]
        contact = Paragraph("<b>077 633 7942</b><br/><b>074 394 6233</b><br/>No. 123, Highlevel Road, Maharagama<br/>bluetechcomputers.lk@gmail.com", info_style)
        header = Table([[header_left, contact]], colWidths=[112 * mm, 68 * mm])
        header.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -1), 1.1, colors.HexColor(BLUE)),
        ]))
        story.append(header)
        story.append(Spacer(1, 6))

        qtitle = Table([[Paragraph("QUOTATION", title),
                         Paragraph(f"<b>Quotation No</b> : {self.qno.get()}<br/><b>Date</b> : {self.qdate.get()}<br/><b>Customer</b> : {self.customer.get()}<br/><b>Phone / WhatsApp</b> : {self.phone.get()}", info_style)]],
                       colWidths=[105 * mm, 75 * mm])
        qtitle.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#F6FAFF")),
            ("BOX", (1, 0), (1, 0), 0.7, colors.HexColor("#B8D8F5")),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(qtitle)
        story.append(Paragraph("BUILD YOUR IDEAL PC WITH US", ParagraphStyle("tag", parent=subtitle, fontSize=7.5, leading=9, textColor=colors.HexColor(BLUE))))
        story.append(Spacer(1, 6))

        data = [["#", "PRODUCT", "PRODUCT DESCRIPTION", "QTY"]]
        for i, (p, d, q, c) in enumerate(items, start=1):
            data.append([str(i), p, d, str(int(q) if float(q).is_integer() else q)])
        t = Table(data, colWidths=[10 * mm, 49 * mm, 103 * mm, 18 * mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BLUE)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.6),
            ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#162A43")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B7C3D0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F7FB")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ALIGN", (0, 0), (0, -1), "CENTER"), ("ALIGN", (-1, 0), (-1, -1), "CENTER"),
        ]))
        story.append(t)
        story.append(Spacer(1, 7))

        p90 = self.num(self.final90.get())
        p180 = self.num(self.final180.get())

        # 90-day warranty is the main selling option; 180-day option is intentionally secondary/smaller.
        warranty90_style = ParagraphStyle("warranty90", parent=styles["BodyText"], fontName="Helvetica-Bold",
                                          fontSize=11, leading=13, textColor=colors.HexColor(DARK_BLUE), alignment=TA_LEFT)
        warranty180_style = ParagraphStyle("warranty180", parent=styles["BodyText"], fontName="Helvetica-Bold",
                                           fontSize=8.5, leading=10, textColor=colors.HexColor(GREEN), alignment=TA_LEFT)
        price90_style = ParagraphStyle("price90", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=15,
                                       leading=17, textColor=colors.white, alignment=TA_CENTER)
        price180_style = ParagraphStyle("price180", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=11,
                                        leading=13, textColor=colors.white, alignment=TA_CENTER)

        w90 = Table([[Paragraph("WITH 90 DAYS<br/>HARDWARE WARRANTY", warranty90_style),
                      Paragraph(money(p90), price90_style)]], colWidths=[68 * mm, 44 * mm])
        w90.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(LIGHT_BLUE)),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#B9DBF8")),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(BLUE)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ]))
        w180 = Table([[Paragraph("WITH 180 DAYS<br/>HARDWARE WARRANTY", warranty180_style),
                       Paragraph(money(p180), price180_style)]], colWidths=[48 * mm, 20 * mm])
        w180.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(LIGHT_GREEN)),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#BEE7CB")),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(GREEN)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        warranty_row = Table([[w90, w180]], colWidths=[112 * mm, 68 * mm])
        warranty_row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(warranty_row)
        story.append(Spacer(1, 7))

        terms = Paragraph("<b>Terms & Conditions</b><br/>• Quotation Validity: Prices are valid for 2 days from the quotation date and time.<br/>• Warranty: Warranty covers MANUFACTURER FAULTS ONLY. Physical damage, burns, liquid damage, and other external damages are not covered.<br/>• Stock Availability: Product availability is subject to change without prior notice.<br/>• Support: For further information or assistance, please contact us by phone or WhatsApp.", small)
        terms_box = Table([[terms, Paragraph("<b>Thank you<br/>for your business!</b>", ParagraphStyle("thanks", parent=normal, fontSize=11, leading=14, alignment=TA_CENTER))]], colWidths=[126 * mm, 54 * mm])
        terms_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F5F9FE")),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#C7D8EA")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(terms_box)
        story.append(Spacer(1, 7))
        story.append(Paragraph("Facebook  |  TikTok  |  Google Reviews                 QUALITY PARTS  |  TRUSTED SERVICE  |  BETTER COMPUTING", small))

        doc.build(story)
        try:
            if sys.platform.startswith("win"):
                os.startfile(filename)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", filename])
            else:
                subprocess.Popen(["xdg-open", filename])
        except Exception:
            pass
        messagebox.showinfo("PDF Created", f"PDF created:\n{filename}\n\nUse the PDF viewer's Share/Send option to send it on WhatsApp.")
        return filename

    def new_quote(self):
        self.editing_id = None
        for w in self.root.winfo_children():
            w.destroy()
        self.rows = []
        self.build()

    def history(self):
        win = tk.Toplevel(self.root)
        win.title("Quotation History")
        win.geometry("980x540")
        tree = ttk.Treeview(win, columns=("q", "customer", "phone", "date", "profit", "p90", "p180"), show="headings")
        headings = ("Quotation No.", "Customer", "Phone", "Date", "Requested Profit", "90 Days", "180 Days")
        for c, h in zip(tree["columns"], headings):
            tree.heading(c, text=h)
            tree.column(c, width=135)
        tree.pack(fill="both", expand=True, padx=10, pady=10)
        c = db()
        for row in c.execute("SELECT id,qno,customer,phone,date,profit,warranty90,warranty180 FROM quotations ORDER BY id DESC"):
            qid, qno, customer, phone, date, profit, p90, p180 = row
            tree.insert("", "end", iid=str(qid), values=(qno, customer, phone, date, money(profit), money(p90), money(p180)))
        c.close()

        ttk.Label(win, text="Double-click a quotation to open and edit it.").pack(pady=(0, 4))
        btns = ttk.Frame(win)
        btns.pack(pady=6)
        ttk.Button(btns, text="OPEN / EDIT SELECTED", command=lambda: self.load_history_item(tree, win)).pack(side="left", padx=5)
        ttk.Button(btns, text="Close", command=win.destroy).pack(side="left", padx=5)
        tree.bind("<Double-1>", lambda e: self.load_history_item(tree, win))

    def load_history_item(self, tree, win):
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("History", "Select a quotation first.", parent=win)
            return
        qid = int(selected[0])
        c = db()
        q = c.execute("SELECT id,qno,customer,phone,date,profit,warranty90,warranty180,weight FROM quotations WHERE id=?", (qid,)).fetchone()
        items = c.execute("SELECT product,description,qty,cost FROM items WHERE quotation_id=? ORDER BY id", (qid,)).fetchall()
        c.close()
        if not q:
            messagebox.showerror("History", "Quotation could not be loaded.", parent=win)
            return

        self.editing_id = q[0]
        self.qno.set(q[1])
        self.customer.set(q[2])
        self.phone.set(q[3])
        self.qdate.set(q[4])
        self.profit.set(str(q[5] or 0))
        self.weight.set(str(q[8] or 0))

        for row in self.rows:
            for w in row[4]:
                w.destroy()
            row[5].destroy()
        self.rows = []
        for p, d, qty, cost in items:
            self.add_row(p, silent=True)
            row = self.rows[-1]
            row[1].set(d or "")
            row[2].set(str(int(qty) if float(qty).is_integer() else qty))
            row[3].set(str(cost or 0))
        if not items:
            self.add_row("", silent=True)
        self.recalc()
        win.destroy()
        self.root.lift()
        self.root.focus_force()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
