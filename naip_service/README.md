# NAIP service (optional)

Adds the "🛰 NAIP" panel to the 2D view (whole file) and the 3D view (patch): aerial image
(RGB / NDVI), trees found by an image model, hand-placed true labels and the labelled area. Separate container because it uses TensorFlow; the tool
works exactly as before without it.

- **Imagery:** NAIP (USDA), RGB + near infrared, 0.6 m, USA only, from Microsoft's Planetary
  Computer (free, no account).
- **Image tree model:** Ventura et al., *Individual tree detection in large-scale urban
  environments using high-resolution multispectral imagery* (github.com/jonathanventura/urban-tree-detection,
  MIT licence; code copied unchanged into `ventura/`). Trained on California. Weights are not in
  git: put the folder `pretrained_rgbn` (weights.best.h5, params.yaml) into `naip_service/weights/`,
  or point `NAIP_WEIGHTS_DIR` in `.env` to the folder that contains it. Without weights the panel
  shows the image only.

Start: `make naip` (dev) or `make prod-naip`.

## True labels (California)

`data/ventura_labels.csv` (96,547 hand-placed tree positions, lon/lat, year, crop) and
`data/ventura_crops.csv` (the 1,651 labelled 154 m image crops) come from
**urban-tree-detection-data** by Jonathan Ventura et al. (github.com/jonathanventura/urban-tree-detection-data),
licensed **CC BY 4.0**, converted from their UTM coordinates to lon/lat. Cities: Bishop, Chico, Claremont,
Eureka, Long Beach, Palm Springs, Riverside, Santa Monica; years 2016 / 2018 / 2020.
Labels exist only inside the crops; the 3D view outlines them.
