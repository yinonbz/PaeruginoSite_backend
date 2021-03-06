from fastapi import APIRouter, Depends, Response, Query, HTTPException
import subprocess, os
import pandas as pd
from fastapi.responses import FileResponse
from app.db.session import get_db
from app.db.crud import (
    get_strain_isolation_mlst, get_strains_names, get_defense_systems_of_genes, get_strains_index,
    get_defense_systems_names, get_colors_dict
)
import numpy as np
from pathlib import Path
from typing import List, Optional
from sorting_techniques import pysort
import hashlib
import json
from pathlib import Path

strains_router = r = APIRouter()


def validate_params(systems, subtree, strains, db_systems):
    all_sys = [x['name'] for x in db_systems]
    systems = [sys for sys in systems if sys in all_sys]
    subtree = [strain for strain in subtree if strain in strains['index']]
    return systems, subtree


def random_color():
    ## this method generate a random color in hex form
    rand = lambda: np.random.randint(100, 255)
    return '#%02X%02X%02X' % (rand(), rand(), rand())


def get_first_layer_offset(x):
    if x > 1100 or x == 0:
        return str(0.08)
    return str(0.00000038 * (x ** 2) - 0.00097175 * x + 0.67964847)


def get_font_size(x):
    """
    this function gets the number of strains the user want to show and return compatible font size
    """
    if (x == 0):
        return str(100)
    return str(0.06 * x + 15.958)


def get_spacing(x):
    """
   this function gets the number of strains the user want to show and return compatible spacing in legend of graph
   """
    if (x == 0):
        return str(2)
    return str(0.001162 * x + 0.311)


def get_offset(x):
    """
       this function gets the number of strains the user want to show and return compatible offset (spacing) between layers
       """
    if (x == 0):
        return str(0.03)
    return str(-0.0001 * x + 0.15)


def get_resolution(x):
    """
           this function gets the number of strains the user want to show and return compatible graph resolution
           """
    if (x == 0):
        return 300
    return 0.183 * x + 23.672


def load_colors():
    """
    this function reads the colors from the DB and save it in dictionary
    for layer coloring
    """
    # Opening JSON file colors.json
    db = next(get_db())
    colors_dict = dict()
    li = get_colors_dict(db)  # json.load(f)
    colors_d = [x['color'] for x in li]
    names = [x['label'] for x in li]
    for (x, col) in zip(names, colors_d):
        colors_dict[x.upper()] = col  # save systems (key) and color(value) in dictionary and return it
    return colors_dict


def load_def_systems_names():
    """
    this function reads the defense systems names from the DB and save it in dictionary
    for layer coloring
    """
    db = next(get_db())
    defense_names = get_defense_systems_names(db, True)
    return list(defense_names)

# sorting object
sortObj = pysort.Sorting()
# load colors to dictionary
colors = load_colors()
def_sys = load_def_systems_names()


@r.get(
    "/",
    # response_model=t.List[StrainBase],
    # response_model_exclude_none=True,
)
async def strains_list(
        response: Response,
        db=Depends(get_db)
):
    """get all the names and assembly id of all strains"""
    strains = get_strains_names(db)
    return strains


@r.get(
    "/indexes",
    # response_model=t.List[StrainBase],
    # response_model_exclude_none=True,
)
async def strains_indexes(
        response: Response,
        db=Depends(get_db)
):
    """Get the index and name of all strains"""
    strains = get_strains_index(db)
    return strains


@r.get(
    "/phyloTree",
    # response_model_exclude_none=True,
)
async def phylogenetic_tree(
        systems: Optional[List[str]] = Query([]),
        subtree: Optional[List[int]] = Query([]),
        MLST: bool = False,
        db=Depends(get_db)
):
    """
    this function handles all requests to generate Phylogenetic tree from browse page in the website.
    the function gets 2 arrays: one for the defense systems and needs to be shows and another to
    subtrees the user might need. if they are empty: the system will show full tree with no defense systems
    on it. this function also generate Dynamic R script in order to generate the tree.
    """
    # validate parameters using DB pre-defined strains and def-systems
    strains = get_strain_isolation_mlst(db)
    db_systems = get_defense_systems_names(db)
    systems, subtree = validate_params(systems, subtree, strains, db_systems)

    # generating filename
    myPath = str(Path().resolve()).replace('\\', '/') + '/static/def_Sys'
    subtreeSort = []
    if len(systems) > 0:
        systems.sort()
    if len(subtree) > 0:
        subtreeSort = sortObj.radixSort(subtree)
    filenameStr = "".join(systems) + "".join(str(x) for x in subtreeSort)
    filenameStr = filenameStr + str(MLST)
    filenameHash = hashlib.md5(filenameStr.encode())
    filename = filenameHash.hexdigest()

    # check if such query allready computed and return it. else, compute new given query.
    if not os.path.exists('static/def_Sys/' + filename + ".png"):
        # prepare POPEN variables needed
        command = 'C:/Program Files/R/R-4.0.4/bin/Rscript.exe'
        # todo replace with command = 'Rscript'  # OR WITH bin FOLDER IN PATH ENV VAR
        arg = '--vanilla'
        # data preprocessing for the R query
        strains['Defense_sys'] = np.random.choice(def_sys, strains.shape[
            0])  # todo remove when defense systems are uploaded to db
        # strains = strains[['index', 'strain', 'Defense_sys']]
        if len(subtree) > 0:
            strains = strains.loc[strains['index'].isin(subtree)]
            systems = strains.loc[strains['Defense_sys'].isin(systems)]['Defense_sys'].unique().tolist() if len(
                systems) > 0 else []
        strains = pd.get_dummies(strains, columns=["Defense_sys"])
        strains.to_csv("static/def_Sys/Defense_sys.csv")

        # R query build-up
        query = """
                    library(ggtreeExtra)
                    ##library(ggstar)
                    library(ggplot2)
                    library(ggtree)
                    library(treeio)
                    library(ggnewscale)
                    library(ape)
                    library(dplyr)

                    trfile <- system.file("extdata","our_tree.tree", package="ggtreeExtra")
                    tree <- read.tree(trfile) """
        if len(subtree) > 0:
            query = query + """
                subtree =c(""" + ",".join('"' + str(x) + '"' for x in subtreeSort) + """)
                tree <- keep.tip(tree,subtree)
                """
        layer = 0
        query = query + """
             dat1 <- read.csv('""" + myPath + """/Defense_sys.csv')
                """
        if MLST is True:
            query = query + """
            # For the clade group
                dat4 <- dat1 %>% select(c("index", "MLST"))
                dat4 <- aggregate(.~MLST, dat4, FUN=paste, collapse=",")
                clades <- lapply(dat4$index, function(x){unlist(strsplit(x,split=","))})
                names(clades) <- dat4$MLST
                
                tree <- groupOTU(tree, clades, "MLST_color")
                MLST <- NULL
                p <- ggtree(tree, layout="circular",branch.length = 'none', open.angle = 10, size = 0.5, aes(color=MLST_color), show.legend=FALSE)
            """
        else:
            query = query + """
                    p <- ggtree(tree, layout="circular",branch.length = 'none', open.angle = 10, size = 0.5)
                            """
        for sys in systems:
            color = colors[sys]
            if (layer == 0):
                query = query + """p <- p + new_scale_colour()+
                                      geom_fruit(
                                        data=dat1,
                                        geom=geom_bar,
                                        mapping=aes(y=index,x=Defense_sys_""" + sys + """, colour=c('""" + color + """')),
                                        orientation="y",
                                        width=1,
                                        pwidth=0.05,
                                        offset = """ + get_first_layer_offset(len(subtreeSort)) + """,
                                        stat="identity",
                                        fill='""" + color + """'
                                      ) + theme(
                                      
                                        legend.text = element_text(size = """ + get_font_size(len(subtreeSort)) + """),
                                        legend.title = element_blank(),
                                        legend.margin=margin(c(0,200,0,0)),
                                        legend.spacing = unit(""" + get_spacing(len(subtreeSort)) + ""","cm"),
                                        legend.spacing.x = unit(""" + get_spacing(len(subtreeSort)) + ""","cm")
                                      )+
                                        scale_colour_manual(values = c('""" + color + """'), labels = c('""" + sys + """'))
                                      """
            if (layer > 0):
                query = query + """p <- p + new_scale_colour()+
                                      geom_fruit(
                                        data=dat1,
                                        geom=geom_bar,
                                        mapping=aes(y=index,x=Defense_sys_""" + sys + """, colour=c('""" + color + """')),
                                        orientation="y",
                                        width=1,
                                        pwidth=0.05,
                                        offset = """ + get_offset(len(subtreeSort)) + """,
                                        stat="identity",
                                        fill='""" + color + """'
                                      ) + theme(
                                        legend.margin=margin(c(0,200,0,0)),
                                        legend.text = element_text(size = """ + get_font_size(len(subtreeSort)) + """),
                                        legend.title = element_blank(),
                                        legend.spacing = unit(""" + get_spacing(len(subtreeSort)) + ""","cm"),
                                        legend.spacing.x = unit(""" + get_spacing(len(subtreeSort)) + ""","cm")
                                      )+
                                        scale_colour_manual(values = c('""" + color + """'), labels = c('""" + sys + """'))
                                      """
            layer += 1

        resolution = get_resolution(len(subtreeSort))
        query = query + """
            dat1$index <- as.character(dat1$index)
            tree <- full_join(tree, dat1, by = c("label" = "index"))
            p <- p %<+% dat1  + geom_tiplab(show.legend=FALSE,aes(label=strain))
            png(""" + '"' + myPath + '/' + filename + """.png", units="cm", width=""" + str(
            resolution) + """, height=""" + str(resolution) + """, res=100)
            plot(p)
            dev.off(0)"""

        # for debugging purpose and error tracking
        print(query)
        f = open("static/def_Sys/" + filename + ".R", "w")
        f.write(query)
        f.close()

        # Execute R query
        try:
            p = subprocess.Popen([command, arg, os.path.abspath("static/def_Sys/" + filename + ".R")],
                                 cwd=os.path.normpath(os.getcwd() + os.sep + os.pardir), stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            output, error = p.communicate()
            return FileResponse('static/def_Sys/' + filename + ".png")

        except Exception as e:
            print("dbc2csv - Error converting file: phylo_tree.R")
            print(e)

            raise HTTPException(status_code=404, detail=e)
    else:
        return FileResponse('static/def_Sys/' + filename + ".png")

    raise HTTPException(status_code=404, detail="e")


@r.get(
    "/strainCircos/{strain_name}",
    response_model_exclude_none=True,
    response_class=FileResponse,
    status_code=200,
)
async def strain_circos_graph(strain_name, response: Response):
    # the structure of the dir file will be stain_name.html and it will be stored in a specific directory.
    if strain_name:
        try:
            split = strain_name.split("(")
            assembly = split[1][:-1]
            print(assembly)
            strain_file = Path("static/Circos/" + assembly + ".html")
            print(strain_file)
            if strain_file.is_file():
                return FileResponse(strain_file, status_code=200)
            else:
                return FileResponse(Path("static/Circos/" + "GCF_000404265.1" + ".html"), status_code=200)
        # if the user inserts a wrong format
        except Exception:
            return Response(content="Wrong Parameters", status_code=400)
    # in the meantime if the file doesn't exist we return a default one
    else:
        # file is not in the directory (the strain name is wrong)
        return FileResponse(Path("static/Circos/" + "GCF_000404265.1" + ".html"), status_code=200)
        # return Response(content="No Results", status_code=400)


@r.get(
    "/strainGenesDefSystems/{strain_name}",
    response_model_exclude_none=True,
    status_code=200,
)
async def get_genes_def_systems(strain_name, response: Response, db=Depends(get_db)):
    if strain_name:
        try:
            split = strain_name.split("(")
            assembly = split[1][:-1]
            df = get_defense_systems_of_genes(db, assembly)
            if df == 'No Results':
                # return Response(content="No Results", status_code=400)
                df = get_defense_systems_of_genes(db, "GCF_000404265.1")
        except Exception:
            df = get_defense_systems_of_genes(db, "GCF_000404265.1")
    return df


@r.get(
    "/defSystemsColors",
    response_model_exclude_none=True,
    status_code=200,
)
async def get_defense_systems_colors(response: Response, db=Depends(get_db)):
    defense_colors = get_colors_dict(db)
    if defense_colors == "No Results":
        return Response(content="No Results", status_code=400)
    return defense_colors
