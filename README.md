# Botonera Virtual de Sons

Aquesta és una aplicació d’escriptori creada amb **Python** que emula una **botonera física**.  
Està dissenyada per a pòdcasts, streamings o qualsevol situació en què calgui **llançar efectes de so ràpidament**.  

El projecte s’ha desenvolupat mitjançant *vibe coding* amb **Google Gemini** i **ChatGPT**,  
i inclou funcions avançades com **assignació de tecles globals**, **perfils configurables** i un **enregistrador d’àudio integrat**.



## Característiques Principals

### Graella Dinàmica  
La interfície suporta diferents formats de graella (de **6x1 a 6x4**) per adaptar-se a les necessitats de l’usuari.

### Configuració per botó  
Amb un clic a qualsevol botó pots:
- Assignar un arxiu de so (`.wav`, `.mp3`)
- Canviar el **nom** i l’**emoji**
- Triar un **color personalitzat**  
Un botó assignat es pot reconfigurar amb el **botó dret**.

### Tecles d’accés ràpid  
Assigna una tecla del teclat per **llançar el so des de qualsevol programa**.

### Enregistrador Integrat  
Enregistra àudio directament des de l’aplicació, desa’l i **assigna’l a un botó buit** — tot dins de l’app.

### Sistema de Perfils  
Desa i carrega diferents configuracions de botons com a fitxers `.json`.  
Perfecte per tenir un perfil per a cada projecte o sessió.

### Control de Volum  
Lliscador de volum general, aplicat a tots els sons actius.

### Portàtil  
El projecte utilitza **camins relatius**, de manera que pots moure la carpeta sencera  
i tot continuarà funcionant sense reiniciar configuracions.


## Instal·lació i Requisits

Aquesta aplicació està feta amb **Python 3.12** (o superior).

### Dependències

Instal·la les llibreries necessàries amb `pip`:

```bash
# Per a la interfície i el so
pip install pygame tkinter

# Per a les tecles globals (hotkeys)
pip install keyboard

# Per a la gravació d'àudio
pip install sounddevice soundfile numpy
