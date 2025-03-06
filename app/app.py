import os
from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'pdf', 'dxf'}

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://///data/blachy.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Ustawiamy folder uploadów jako absolutną ścieżkę
upload_folder = os.path.join(app.root_path, 'uploads')
app.config['UPLOAD_FOLDER'] = upload_folder
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

app.secret_key = 'your_secret_key'

db = SQLAlchemy(app)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


class MaterialOption(db.Model):
    __tablename__ = 'material_option'
    id = db.Column(db.Integer, primary_key=True)
    nazwa = db.Column(db.String(100), unique=True, nullable=False)

class ThicknessOption(db.Model):
    __tablename__ = 'thickness_option'
    id = db.Column(db.Integer, primary_key=True)
    wartosc = db.Column(db.String(50), unique=True, nullable=False)

class Blacha(db.Model):
    __tablename__ = 'blacha'
    id = db.Column(db.Integer, primary_key=True)
    nazwa = db.Column(db.String(100), nullable=False)
    nazwa_prosta = db.Column(db.String(100), nullable=True)
    kod = db.Column(db.String(50), nullable=False, unique=True)
    stan_obecny = db.Column(db.Integer, nullable=False)
    # Zamiast tekstowych pól material i grubosc używamy kluczy obcych:
    material_id = db.Column(db.Integer, db.ForeignKey('material_option.id'), nullable=True)
    thickness_id = db.Column(db.Integer, db.ForeignKey('thickness_option.id'), nullable=True)
    rodzaj_obrobki = db.Column(db.String(50), nullable=True)
    pdf_filename = db.Column(db.String(200), nullable=True)
    dxf_filename = db.Column(db.String(200), nullable=True)
    project_items = db.relationship("ProjectItem", back_populates="blacha", lazy=True)

    @property
    def material(self):
        if self.material_id:
            m = MaterialOption.query.get(self.material_id)
            return m.nazwa if m else None
        return None

    @property
    def grubosc(self):
        if self.thickness_id:
            t = ThicknessOption.query.get(self.thickness_id)
            return t.wartosc if t else None
        return None

    @property
    def stan_potrzebny(self):
        # Suma zapotrzebowania z wpisów projektowych
        return sum(item.ilosc for item in self.project_items)


# MODELE DLA PROJEKTÓW
class Project(db.Model):
    __tablename__ = 'project'
    id = db.Column(db.Integer, primary_key=True)
    nazwa = db.Column(db.String(100), nullable=False)
    items = db.relationship("ProjectItem", backref="project", lazy=True)

class ProjectItem(db.Model):
    __tablename__ = 'project_item'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    blacha_id = db.Column(db.Integer, db.ForeignKey("blacha.id"), nullable=False)
    ilosc = db.Column(db.Integer, nullable=False)
    blacha = db.relationship("Blacha", back_populates="project_items")

# GŁÓWNE TRASY DLA BLACH (istniejące)
@app.route('/')
def index():
    blachy = Blacha.query.all()
    return render_template('index.html', blachy=blachy)


@app.route('/dodaj', methods=['GET', 'POST'])
def dodaj():
    if request.method == 'POST':
        nowa_blacha = Blacha(
            nazwa=request.form['nazwa'],
            nazwa_prosta=request.form['nazwa_prosta'],
            kod=request.form['kod'],
            stan_obecny=int(request.form['stan_obecny']),
            material_id=int(request.form['material_id']),
            thickness_id=int(request.form['thickness_id']),
            rodzaj_obrobki=request.form['rodzaj_obrobki']
        )
        db.session.add(nowa_blacha)
        db.session.commit()
        return redirect(url_for('index'))
    materials = MaterialOption.query.all()
    thicknesses = ThicknessOption.query.all()
    return render_template('dodaj.html', materials=materials, thicknesses=thicknesses)


@app.route('/materialy')
def materialy():
    materials = MaterialOption.query.all()
    thicknesses = ThicknessOption.query.all()
    return render_template('materialy.html', materials=materials, thicknesses=thicknesses)

@app.route('/materialy/dodaj_material', methods=['GET', 'POST'])
def dodaj_material():
    if request.method == 'POST':
        nazwa = request.form['nazwa']
        new_material = MaterialOption(nazwa=nazwa)
        db.session.add(new_material)
        db.session.commit()
        return redirect(url_for('materialy'))
    return render_template('dodaj_material.html')

@app.route('/materialy/dodaj_thickness', methods=['GET', 'POST'])
def dodaj_thickness():
    if request.method == 'POST':
        wartosc = request.form['wartosc']
        new_thickness = ThicknessOption(wartosc=wartosc)
        db.session.add(new_thickness)
        db.session.commit()
        return redirect(url_for('materialy'))
    return render_template('dodaj_thickness.html')

@app.route('/upload/<int:blacha_id>', methods=['GET', 'POST'])
def upload_file(blacha_id):
    blacha = Blacha.query.get_or_404(blacha_id)
    if request.method == 'POST':
        if 'pdf' in request.files:
            file_pdf = request.files['pdf']
            if file_pdf and allowed_file(file_pdf.filename) and file_pdf.filename.lower().endswith('.pdf'):
                filename = secure_filename(file_pdf.filename)
                pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file_pdf.save(pdf_path)
                blacha.pdf_filename = filename
        if 'dxf' in request.files:
            file_dxf = request.files['dxf']
            if file_dxf and allowed_file(file_dxf.filename) and file_dxf.filename.lower().endswith('.dxf'):
                filename = secure_filename(file_dxf.filename)
                dxf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file_dxf.save(dxf_path)
                blacha.dxf_filename = filename
        db.session.commit()
        flash('Pliki zostały załadowane')
        return redirect(url_for('index'))
    return render_template('upload.html', blacha=blacha)


@app.route('/files/<filename>')
def uploaded_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    return send_file(file_path)


# Trasa generująca ofertę na braki (z poprzedniego przykładu)
@app.route('/generate_txt', methods=['POST'])
def generate_txt():
    # Pobierz listę id blach zaznaczonych przez użytkownika
    overrides = request.form.getlist("override")
    try:
        overrides = set(int(x) for x in overrides)
    except ValueError:
        overrides = set()

    # Pobierz wszystkie blachy
    all_blachy = Blacha.query.all()
    # Zbiór blach do oferty: jeśli jest override lub mają niedobór
    offer_items = []
    for b in all_blachy:
        if b.id in overrides or b.stan_obecny < b.stan_potrzebny:
            offer_items.append(b)

    if not offer_items:
        flash("Nie ma blach do oferty!")
        return redirect(url_for('index'))

    header = "Oferta Na Braki:\n"
    separator = "----------------------------------------------------------\n"
    col_headers = "{:<4}{:<8}{:<12}{:<10}{:<15}\n".format("lp.", "KOD", "Materiał", "Grubość", "Brak (szt.)")
    content = header + separator + col_headers + separator

    for i, b in enumerate(offer_items, start=1):
        if b.id in overrides:
            missing_str = "X szt."
        else:
            missing = b.stan_potrzebny - b.stan_obecny
            missing_str = f"{missing} szt."
        content += "{:<4}{:<8}{:<12}{:<10}{:<15}\n".format(i, b.kod, b.material, b.grubosc, missing_str)

    txt_path = os.path.join(app.config['UPLOAD_FOLDER'], 'oferta_braki.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return send_file(txt_path, as_attachment=True)


# ---- SEKCJA PROJEKTY ----

# Lista projektów
@app.route('/projekty')
def projekty():
    projekty = Project.query.all()
    return render_template('projekty.html', projekty=projekty)


# Dodawanie nowego projektu
@app.route('/projekty/dodaj', methods=['GET', 'POST'])
def dodaj_projekt():
    if request.method == 'POST':
        nowy_projekt = Project(nazwa=request.form['nazwa'])
        db.session.add(nowy_projekt)
        db.session.commit()
        return redirect(url_for('projekty'))
    return render_template('dodaj_projekt.html')


# Szczegóły projektu – wyświetlenie i dodawanie pozycji (blach)
@app.route('/projekty/<int:projekt_id>', methods=['GET', 'POST'])
def projekt_szczegoly(projekt_id):
    projekt = Project.query.get_or_404(projekt_id)
    # Pobierz wszystkie wpisy (pozycje) tego projektu
    if request.method == 'POST':
        # Formularz do dodania pozycji w projekcie
        blacha_id = int(request.form['blacha_id'])
        ilosc = int(request.form['ilosc'])
        nowy_element = ProjectItem(project_id=projekt.id, blacha_id=blacha_id, ilosc=ilosc)
        db.session.add(nowy_element)
        db.session.commit()
        return redirect(url_for('projekt_szczegoly', projekt_id=projekt.id))
    # Pobierz listę wszystkich dostępnych blach, aby umożliwić wybór w formularzu
    wszystkie_blachy = Blacha.query.all()
    return render_template('projekt_szczegoly.html', projekt=projekt, blachy=wszystkie_blachy)

@app.route('/projekty/item/edit/<int:item_id>', methods=['GET', 'POST'])
def edit_project_item(item_id):
    item = ProjectItem.query.get_or_404(item_id)
    if request.method == 'POST':
        # Aktualizujemy wpis projektu:
        # Użytkownik może wybrać inną blachę oraz zmienić ilość wymaganych sztuk
        item.blacha_id = int(request.form['blacha_id'])
        item.ilosc = int(request.form['ilosc'])
        db.session.commit()
        return redirect(url_for('projekt_szczegoly', projekt_id=item.project_id))
    else:
        all_blachy = Blacha.query.all()
        return render_template('edit_project_item.html', item=item, blachy=all_blachy)

@app.route('/edytuj/<int:blacha_id>', methods=['GET', 'POST'])
def edytuj_blacha(blacha_id):
    blacha = Blacha.query.get_or_404(blacha_id)
    if request.method == 'POST':
        blacha.nazwa = request.form['nazwa']
        blacha.nazwa_prosta = request.form['nazwa_prosta']
        blacha.kod = request.form['kod']
        blacha.stan_obecny = int(request.form['stan_obecny'])
        blacha.material_id = int(request.form['material_id'])
        blacha.thickness_id = int(request.form['thickness_id'])
        blacha.rodzaj_obrobki = request.form['rodzaj_obrobki']
        db.session.commit()
        return redirect(url_for('index'))
    # Pobierz listę dostępnych materiałów i grubości
    materials = MaterialOption.query.all()
    thicknesses = ThicknessOption.query.all()
    return render_template('edytuj.html', blacha=blacha, materials=materials, thicknesses=thicknesses)

@app.route('/usun/<int:blacha_id>', methods=['POST'])
def usun_blacha(blacha_id):
    blacha = Blacha.query.get_or_404(blacha_id)
    db.session.delete(blacha)
    db.session.commit()
    flash("Blacha została usunięta")
    return redirect(url_for('index'))


if __name__ == '__main__':
    with app.app_context():
        # Opcjonalnie: db.drop_all()  # Usuń tylko jeśli chcesz zresetować bazę
        db.create_all()

        # Sprawdź, czy w tabeli material_option nie ma jeszcze rekordu "Stal"
        if not MaterialOption.query.filter_by(nazwa="Stal").first():
            stal = MaterialOption(nazwa="Stal")
            db.session.add(stal)
        if not MaterialOption.query.filter_by(nazwa="Aluminium").first():
            aluminium = MaterialOption(nazwa="Aluminium")
            db.session.add(aluminium)
        db.session.commit()

        # Sprawdź i dodaj opcje grubości, jeśli nie istnieją
        if not ThicknessOption.query.filter_by(wartosc="3mm").first():
            t3mm = ThicknessOption(wartosc="3mm")
            db.session.add(t3mm)
        if not ThicknessOption.query.filter_by(wartosc="2mm").first():
            t2mm = ThicknessOption(wartosc="2mm")
            db.session.add(t2mm)
        if not ThicknessOption.query.filter_by(wartosc="5mm").first():
            t5mm = ThicknessOption(wartosc="5mm")
            db.session.add(t5mm)
        db.session.commit()

        # Dodaj przykładowe blachy tylko, gdy nie ma ich jeszcze
        if Blacha.query.count() == 0:
            stal = MaterialOption.query.filter_by(nazwa="Stal").first()
            aluminium = MaterialOption.query.filter_by(nazwa="Aluminium").first()
            t3mm = ThicknessOption.query.filter_by(wartosc="3mm").first()
            t2mm = ThicknessOption.query.filter_by(wartosc="2mm").first()
            t5mm = ThicknessOption.query.filter_by(wartosc="5mm").first()

            przykładowe_blachy = [
                Blacha(nazwa="Blacha A", nazwa_prosta="kątownik", kod="A001", stan_obecny=10,
                       material_id=stal.id, thickness_id=t3mm.id, rodzaj_obrobki="CNC"),
                Blacha(nazwa="Blacha B", nazwa_prosta="płyta", kod="B001", stan_obecny=20,
                       material_id=aluminium.id, thickness_id=t2mm.id, rodzaj_obrobki="Palenie"),
                Blacha(nazwa="Blacha C", nazwa_prosta="blacha robocza", kod="C001", stan_obecny=5,
                       material_id=stal.id, thickness_id=t5mm.id, rodzaj_obrobki="Gięcie + Palenie"),
            ]
            db.session.add_all(przykładowe_blachy)
            db.session.commit()
    app.run(debug=True, host='0.0.0.0')
