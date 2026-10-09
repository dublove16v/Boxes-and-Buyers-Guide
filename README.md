# Boxes and Buyer's Guide Tool

Streamlit desk for printing FTC buyers guides from the weekly boxes sheet and a DealerTrack inventory report.

- Upload the week's boxes file (`.xlsx`, `.xls`, or `.csv`). The newest uploaded week opens first.
- Cars crossed off on the sheet stay on the list and are marked Dead. They are not printed.
- Check HERE and CHIP/BG for each car. Those checks are saved on the app.
- 2017 and newer prints dealer warranty, limited. 2016 and older prints As-Is and a service contract.
- Upload a DealerTrack report for cars that did not come from the auction.
- Check Print, download the HTML file, and it opens the print dialog. Use letter paper at 100% scale.

## Publish on Streamlit

1. Open [share.streamlit.io](https://share.streamlit.io).
2. Create an app from this GitHub repo.
3. Main file: `app.py`. Branch: `main`.

HERE, CHIP/BG, uploaded weeks, and the DealerTrack list are stored in the app database, not in this public repo.
