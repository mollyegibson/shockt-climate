"""2024–2025 monthly country trends, keeping air and sea separate."""
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import nbformat
from datetime import datetime

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"outputs/emissions"
cells=list(csv.DictReader((OUT/"international_monthly_port.csv").open()))
totals=defaultdict(lambda:[0.,0.,0.])
for r in cells:
    if r["month"][:4] not in ("2024","2025"):
        continue
    v=totals[(r["month"],r["iso3"],r["mode"])]
    v[0]+=float(r["weight_t"])
    if r["route_supported"]=="True":
        v[1]+=float(r["weight_t"])
        v[2]+=float(r["equal_node_rf_kg_co2e"])/1000
rows=[]
for (month,country,mode),(mass,covered,emissions) in sorted(totals.items()):
    rows.append(dict(month=month,country=country,mode=mode,reported_weight_t=mass,
                     supported_weight_t=covered,coverage=covered/mass,
                     estimated_international_t_co2e=emissions if covered else None))
with (OUT/"country_mode_monthly_trends_2024_2025.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
lookup={(r["month"],r["country"],r["mode"]):r for r in rows}
months=[f"{y}-{m:02d}-01" for y in (2024,2025) for m in range(1,13)]
dates=[datetime.fromisoformat(m) for m in months]
countries={"CHN":("China","#2864dc"),"THA":("Thailand","#ed8b23"),
           "KOR":("South Korea","#13a49b"),"JPN":("Japan","#a855c7"),
           "TWN":("Taiwan","#d74949"),"IND":("India","#6e8422")}
plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False})


def draw(selected,name,title):
    fig,axes=plt.subplots(2,2,figsize=(13,8),sharex=True)
    for col,mode in enumerate(("air","vessel")):
        for row,field,ylabel in ((0,"reported_weight_t","Reported import weight (tonnes)"),
                                 (1,"estimated_international_t_co2e","Estimated international tonnes CO₂e")):
            ax=axes[row,col]
            for country in selected:
                label,color=countries[country]
                values=[]
                for m in months:
                    record=lookup.get((m,country,mode))
                    # Missing records/unsupported emissions remain gaps, not zero estimates.
                    val=record[field] if record else None
                    values.append(float("nan") if val is None else val)
                ax.plot(dates,values,label=label,color=color,linewidth=2)
            ax.set_title(("Air freight" if mode=="air" else "Sea freight")+" — "+("weight" if row==0 else "estimated emissions"))
            ax.set_ylabel(ylabel);ax.set_ylim(bottom=0)
            ax.axvline(datetime(2025,1,1),color="#999999",linestyle=":",linewidth=1)
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
            ax.grid(axis="y",alpha=.15)
    handles,labels=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc="lower center",ncol=len(selected),bbox_to_anchor=(.5,.055))
    fig.suptitle(title,weight="bold",fontsize=15)
    fig.text(.06,.025,"Air and sea have separate scales. Fixed factors; equal departure-node scenario; air includes RF. Missing routes excluded.",fontsize=9)
    fig.tight_layout(rect=[0,.1,1,.94])
    fig.savefig(OUT/name,dpi=160,bbox_inches="tight");plt.close(fig)


draw(countries,"08_country_monthly_trends.png","Compressor country trends, 2024–2025: air and sea shown separately")
draw(["THA"],"09_thailand_monthly_trends.png","Thailand compressors, 2024–2025: rising ocean flows and falling air flows")
text="""## Country and mode trends: January 2024–December 2025

Monthly charts separate **air** and **sea**, showing reported weight above and estimated international
emissions below. The same six country colors are used in every panel; the CSV includes all configured
countries with observations. Each panel has its own vertical scale. Gaps are missing observations or
unsupported emissions, not measured zero emissions. The charts are descriptive, not seasonally adjusted.

Thailand illustrates why volume and carbon can move differently. In May–December 2025 versus the same
months of 2024, its **sea weight rose from 5,025.6 to 5,725.0 tonnes (+13.9%)**, while
**air weight fell from 140.0 to 63.5 tonnes (−54.6%)**. Total air/sea weight rose 12.1%.
Air's factor per tonne-km is much higher than sea's. The observed mode shift therefore helps explain
why the scenario estimate for Thailand's supported international flows falls from about **3,683 to
2,949 tonnes CO₂e**, despite higher total weight. These totals use all supported arrivals in each period;
coverage and port composition can change, so they are not the fixed common-support headline comparison.

The finished-refrigerator production evidence is separate from compressor trade. No production transfer,
company shipment route, tariff causation or measured emissions inventory is established here.
"""
(ROOT/"COUNTRY_TRENDS.md").write_text(text+"\n\n![Country trends](outputs/emissions/08_country_monthly_trends.png)\n\n![Thailand trends](outputs/emissions/09_thailand_monthly_trends.png)\n")
with (OUT/"README.md").open("a") as f:
    f.write("\n\n"+text+"\n\n![Country trends](08_country_monthly_trends.png)\n\n![Thailand trends](09_thailand_monthly_trends.png)\n")
nb=nbformat.read(ROOT/"compressor_emissions.ipynb",as_version=4)
nb.cells.append(nbformat.v4.new_markdown_cell(text))
for name in ("08_country_monthly_trends.png","09_thailand_monthly_trends.png"):
    nb.cells.append(nbformat.v4.new_code_cell(f"display(Image(filename=str(output/'{name}')))") )
nbformat.write(nb,ROOT/"compressor_emissions.ipynb")
print("Saved country/mode monthly CSV and two trend charts for 2024–2025")
