#!/usr/bin/python3.7
import pandas as pd
import numpy as np
import scipy as sp
import glog as log
import glob
import os
import cfg_builder
import threading
from typing import List, Dict
from utils import delCodeSegLog, list2Str


class AcfgWorker(threading.Thread):
    """Handle/convert a batch of binary to ACFG"""

    def __init__(self, pathPrefix: str,
                 binaryIds: List[str],
                 id2Label: Dict[str, str]) -> None:
        super(AcfgWorker, self).__init__()
        self.seenInst: set = set()
        self.pathPrefix: str = pathPrefix
        self.binaryIds: List[str] = binaryIds
        self.id2Label: Dict[str, str] = id2Label

    def exportSeenInst(self, exportTo: str) -> None:
        instColumn = {'Inst': sorted(list(self.seenInst))}
        df = pd.DataFrame(data=instColumn)
        df.to_csv('%s.csv' % exportTo)

    def discoverInstDictionary(self, exportTo: str) -> None:
        idCnt = len(self.binaryIds)
        for (i, bId) in enumerate(self.binaryIds):
            log.info(f'[DiscoverInstDict] Processing {i}/{idCnt} {bId}.asm')
            cfgBuilder = cfg_builder.ControlFlowGraphBuilder(bId,
                                                             self.pathPrefix)
            cfgBuilder.parseInstructions()
            instCnt = len(cfgBuilder.instBuilder.seenInst)
            log.debug(f'[DiscoverInstDict] Found {instCnt} unique insts')
            self.seenInst = self.seenInst.union(cfgBuilder.instBuilder.seenInst)

        self.exportSeenInst(exportTo)

    def run(self) -> None:
        idCnt = len(self.binaryIds)
        for (i, bId) in enumerate(self.binaryIds):
            log.info(f'[{self.name}] Processing {i + 1}th/{idCnt} binary')
            if bId not in self.id2Label:
                log.error(f'Unable to label program {bId}')
                continue

            acfgBuilder = cfg_builder.AcfgBuilder(bId, self.pathPrefix)
            features, adjMatrix = acfgBuilder.getAttributedCfg()
            filePrefix = self.pathPrefix + '/' + bId
            np.savetxt(filePrefix + '.features.txt', features, fmt="%d")
            np.savetxt(filePrefix + '.label.txt',
                       np.array([self.id2Label[bId]]), fmt="%s")
            sp.sparse.save_npz(filePrefix + '.adjacent', adjMatrix)

        log.info(f'[{self.name}] Generated {idCnt} ACFGs')


class AcfgMaster(object):

    def __init__(self,
                 pathPrefix: str,
                 labelPath: str = '',
                 binaryIds: List[str] = None) -> None:
        super(AcfgMaster, self).__init__()
        self.pathPrefix = pathPrefix
        self.labelPath = labelPath
        delCodeSegLog()
        self.id2Label: Dict[str, str] = self.loadLabel()
        if binaryIds is None:
            self.binaryIds: List[str] = self.loadDefaultBinaryIds()
        else:
            self.binaryIds = binaryIds

        self.workers: List[AcfgWorker] = []

    def loadLabel(self) -> Dict[str, str]:
        df = pd.read_csv(self.labelPath, header=0,
                         dtype={'Id': str, 'Class': str})
        id2Label = {k.lstrip('"').rstrip('"'): v
                    for (k, v) in zip(df['Id'], df['Class'])}
        return id2Label

    def loadDefaultBinaryIds() -> List[str]:
        binaryIds = []
        for path in glob.glob(self.pathPrefix + '/*.asm', recursive=False):
            filename = path.split('/')[-1]
            id = filename.split('.')[0]
            binaryIds.append(id)

        return binaryIds

    def dispatchWorkers(self, numWorkers: int) -> None:
        bIdPerWorker = len(self.binaryIds) // numWorkers
        for i in range(0, len(self.binaryIds), bIdPerWorker):
            endIdx = min(i + bIdPerWorker, len(self.binaryIds))
            binaryIdBatch = self.binaryIds[i: endIdx]
            worker = AcfgWorker(self.pathPrefix, binaryIdBatch, self.id2Label)
            self.workers.append(worker)
            worker.start()

        for worker in self.workers:
            worker.join()

        self.aggregateDgcnnFormat()
        self.clearTmpFiles()

    def aggregateDgcnnFormat(self) -> None:
        log.info(f"[AggrDgcnnFormat] Aggregate ACFGs to txt format")
        numBinaries = len(self.binaryIds)
        output = open(self.pathPrefix + '/' + 'Acfg.txt', 'w')
        output.write("%d\n" % numBinaries)
        for (i, bId) in enumerate(self.binaryIds):
            log.info(f"[AggrDgcnnFormat] Processing {i + 1}th/{numBinaries} ACFG")
            filePrefix = self.pathPrefix + '/' + bId
            label = np.loadtxt(filePrefix + '.label.txt',
                               dtype=int, ndmin=1)[0]
            features = np.loadtxt(filePrefix + '.features.txt',
                                  dtype=int, ndmin=2)
            sp_adjacent_mat = sp.sparse.load_npz(filePrefix + '.adjacent.npz')
            output.write("%d %d\n" % (features.shape[0], label))

            sp_adjacent = sp.sparse.find(sp_adjacent_mat)
            indices = {}
            for i in range(len(sp_adjacent[0])):
                if sp_adjacent[0][i] not in indices:
                    indices[sp_adjacent[0][i]] = []

                indices[sp_adjacent[0][i]].append(sp_adjacent[1][i])

            for (i, feature) in enumerate(features):
                neighbors = indices[i] if i in indices else []
                output.write("1 %d %s\n" %
                             (len(neighbors), list2Str(neighbors, feature)))

        output.close()
        log.info(f"[AggrDgcnnFormat] Converted {numBinaries} ACFGs")

    def clearTmpFiles(self) -> None:
        log.info(f"[ClearTmpFiles] Remove temporary files ****")
        for (i, bId) in enumerate(self.binaryIds):
            filePrefix = self.pathPrefix + '/' + bId
            for ext in ['.label.txt', '.features.txt', '.adjacent.npz']:
                os.remove(filePrefix + ext)

        log.info(f"[ClearTmpFiles] {len(self.binaryIds)} files removed ****")


if __name__ == '__main__':
    log.setLevel("INFO")
    pathPrefix = '../TrainSet'
    worker = AcfgWorker(pathPrefix, [], '../trainLabels.csv')
    worker.run()