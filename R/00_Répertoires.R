library(camtrapR)
library(fs)

# Lecture de la liste des stations et des caméras
postes <- read.csv(file = "postes_qgis.csv")

# Répertoires des photos téléchargées des caméras
photo_brutes <- path_abs("../photos_brutes")

# Création des répertoires d'images d'origine
stations <- createStationFolders (
  inDir = photo_brutes,
  stations = as.character(postes$Station),
  cameras = as.character(postes$Camera),
  createinDir = FALSE
)

# # Répertoires des photos renommées
# photo_renommees <- path_abs("../photos_renommees")
# 
# # Renommage des photos
# renommage <- imageRename(
#   inDir = photo_brutes,
#   outDir = photo_renommees,
#   hasCameraFolders = TRUE,
#   keepCameraSubfolders = TRUE,
#   copyImages = TRUE,
#   writecsv = TRUE
# )
# 
# exifTagNames(
#   fileName = path_abs(
#     "/mnt/data/Digikam/CameraTraps/photos_brutes/FR38_Saint-Mury-Monteymond/Refuge_du_Pré_du_Molard_01/DSCF0004.JPG"
#   )
# )

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
