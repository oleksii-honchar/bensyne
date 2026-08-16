import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { EventEmitterModule } from '@nestjs/event-emitter';
import { AppBootstrapService } from './app-bootstrap.service';
import { AppConfig } from './app.config';
import { validateAppEnv } from './app.env.validation';
import { ForceReprocessService } from './application/force-reprocess.service';
import { EnhancementPipelineService } from './application/services/enhancement-pipeline.service';
import { ImportanceScoringService } from './application/services/importance-scoring.service';
import { TagExtractionService } from './application/services/tag-extraction.service';
import { AgentSessionChunkingStrategy } from './application/strategies/agent-session-chunking.strategy';
import { MastraChunkingService } from './application/strategies/mastra-chunking.service';
import { ObsidianChunkingStrategy } from './application/strategies/obsidian-chunking.strategy';
import { StrategyRouter } from './application/strategies/strategy-router.service';

import { ConfigurationModule } from './infrastructure/config/configuration.module';
import { LoggerModule } from './infrastructure/logging/logger.module';
import { PrismaModule } from './infrastructure/prisma/prisma.module';
import { FileMemoryTrackerRepository } from './infrastructure/repositories/file-memory-tracker.repository';
import { BensyneClient } from './infrastructure/services/bensyne-client.service';
import { FileHasherService } from './infrastructure/services/file-hasher.service';
import { FileMemoryTrackerService } from './infrastructure/services/file-memory-tracker.service';
import { FileProcessingQueue } from './infrastructure/services/file-processing-queue.service';
import { FileWatcherService } from './infrastructure/services/file-watcher.service';
import { GracefulShutdownService } from './infrastructure/services/graceful-shutdown.service';
import { HardwareIdDetectorService } from './infrastructure/services/hardware-id-detector.service';
import { SessionMetadataService } from './infrastructure/services/session-metadata.service';
import { ChunkContentUseCase } from './use-cases/chunk-content.use-case';
import { IngestChunkUseCase } from './use-cases/ingest-chunk.use-case';
import { ProcessFileUseCase } from './use-cases/process-file.use-case';

@Module({
  imports: [
    ConfigModule.forRoot({
      load: [AppConfig],
      isGlobal: true,
      validate: validateAppEnv,
    }),
    EventEmitterModule.forRoot({
      wildcard: false,
      delimiter: '.',
      maxListeners: 20,
      verboseMemoryLeak: false,
      ignoreErrors: false,
    }),
    LoggerModule.forRootAsync(),
    ConfigurationModule,
    PrismaModule,
  ],
  controllers: [],
  providers: [
    AppBootstrapService,
    FileWatcherService,
    GracefulShutdownService,

    // Use cases
    ChunkContentUseCase,
    ProcessFileUseCase,
    IngestChunkUseCase,

    // Chunking
    MastraChunkingService,
    AgentSessionChunkingStrategy,
    ObsidianChunkingStrategy,
    StrategyRouter,

    // Enhancement pipeline
    EnhancementPipelineService,
    ImportanceScoringService,
    TagExtractionService,

    // Application services
    ForceReprocessService,

    // Infrastructure
    FileProcessingQueue,
    BensyneClient,

    // File→Memory tracking
    FileMemoryTrackerRepository,
    FileMemoryTrackerService,

    // File hash and hardware ID
    FileHasherService,
    HardwareIdDetectorService,

    // Session metadata
    SessionMetadataService,
  ],
})
export class AppModule {}
