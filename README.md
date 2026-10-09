# Boxes and Buyer's Guide Tool

Streamlit desk for printing FTC buyers guides from the weekly boxes sheet and a DealerTrack inventory report.

- The app opens with the BOXES folder already loaded, from 2021 through the current week. The newest week is selected first.
- Upload a newer boxes file (`.xlsx`, `.xls`, or `.csv`) when the week changes. An Excel upload keeps cars that were crossed off; those stay on the list as dead deals and are not printed.
- Check HERE and CHIP/BG for each car. Those checks are saved on the app.
- 2017 and newer prints dealer warranty, limited. 2016 and older prints As-Is and a service contract.
- Upload a DealerTrack report for cars that did not come from the auction.
- Check Print, download the HTML file, and it opens the print dialog. Use letter paper at 100% scale.

## Publish on Streamlit

1. Open [share.streamlit.io](https://share.streamlit.io).
2. Create an app from this GitHub repo.
3. Main file: `app.py`. Branch: `main`.

HERE, CHIP/BG, later uploads, and the DealerTrack list stay in the app database. The starting weeks in `seed/csv` are included so Streamlit opens with the folder already loaded. This repo is public, so those inventory VINs are visible on GitHub. Streamlit can also deploy a private repo if you want that hidden later.
