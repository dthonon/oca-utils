library(camtrapR)
library(fs)

base_dir <- "/media/data/Digikam/CameraTraps/"
dest_dir <- "/media/data/camtrapr"

# Lecture de la liste des stations et des caméras
postes <- read.csv(file = path(base_dir, "Gestion_photos", "postes_qgis.csv"))

# Répertoires des photos téléchargées des caméras
photo_brutes <- path(base_dir, "photos_brutes")

# Répertoires des photos renommées
photo_renommees <- path(dest_dir)

# Renommage des photos
renommage <- imageRename(
  inDir = photo_brutes,
  outDir = photo_renommees,
  hasCameraFolders = TRUE,
  keepCameraSubfolders = TRUE,
  copyImages = TRUE,
  writecsv = TRUE
)

# Lecture des tags d'identification d'espèce
table_photos <- recordTable(
  inDir = photo_brutes,
  IDfrom = "metadata",
  cameraID = "directory",
  camerasIndependent = TRUE,
  timeZone = "Europe/Paris",
  metadataSpeciesTag = "Nature"
)

# Etat opérationnel des caméras
operation_cameras <- cameraOperation(
  CTtable = postes,
  stationCol = "Station",
  cameraCol = "Camera",
  setupCol = "Debut",
  retrievalCol = "Fin",
  byCamera = FALSE,
  allCamsOn = FALSE,
  camerasIndependent = TRUE,
  dateFormat = "%Y/%m/%d"
)
camtrapR:::camopPlot(camOp = operation_cameras)

# Synthèse
rapport <- surveyReport(
  recordTable = table_photos,
  CTtable = postes,
  camOp = operation_cameras,
  speciesCol = "Species",
  stationCol = "Station",
  cameraCol = "Camera",
  setupCol = "Debut",
  retrievalCol = "Fin",
  CTDateFormat = "%Y/%m/%d",
  recordDateTimeCol = "DateTimeOriginal",
  recordDateTimeFormat = "%Y-%m-%d %H:%M:%S",
  Xcol = "X",
  Ycol = "Y"
)

rapport$species_by_station
rapport$events_by_species
