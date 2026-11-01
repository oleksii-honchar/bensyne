-- CreateTable
CREATE TABLE "FileTracker" (
    "id" BIGINT NOT NULL PRIMARY KEY,
    "filePath" TEXT NOT NULL,
    "sourceId" TEXT NOT NULL,
    "memoryBank" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    "fileHash" TEXT,
    "hardwareId" TEXT
);

-- CreateTable
CREATE TABLE "FileMemoryTracker" (
    "id" BIGINT NOT NULL PRIMARY KEY,
    "memoryId" TEXT NOT NULL,
    "fileTrackerId" BIGINT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "FileMemoryTracker_fileTrackerId_fkey" FOREIGN KEY ("fileTrackerId") REFERENCES "FileTracker" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateIndex
CREATE INDEX "FileTracker_filePath_idx" ON "FileTracker"("filePath");

-- CreateIndex
CREATE INDEX "FileTracker_sourceId_memoryBank_idx" ON "FileTracker"("sourceId", "memoryBank");

-- CreateIndex
CREATE INDEX "FileTracker_fileHash_idx" ON "FileTracker"("fileHash");

-- CreateIndex
CREATE INDEX "FileTracker_hardwareId_idx" ON "FileTracker"("hardwareId");

-- CreateIndex
CREATE UNIQUE INDEX "FileTracker_filePath_key" ON "FileTracker"("filePath");

-- CreateIndex
CREATE INDEX "FileMemoryTracker_fileTrackerId_idx" ON "FileMemoryTracker"("fileTrackerId");

-- CreateIndex
CREATE UNIQUE INDEX "FileMemoryTracker_fileTrackerId_memoryId_key" ON "FileMemoryTracker"("fileTrackerId", "memoryId");

