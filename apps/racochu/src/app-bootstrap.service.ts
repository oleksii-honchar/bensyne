import { Inject, Injectable, OnApplicationBootstrap } from '@nestjs/common';
import * as os from 'os';
import * as path from 'path';
import { ConfigurationService } from './infrastructure/config/configuration.service';
import { BasePinoLogger } from './infrastructure/logging/base-pino-logger';

@Injectable()
export class AppBootstrapService implements OnApplicationBootstrap {
  constructor(
    @Inject('CONFIG_FILE_PATH') private readonly configFilePath: string,
    private readonly configService: ConfigurationService,
    private readonly logger: BasePinoLogger,
  ) {}

  async onApplicationBootstrap(): Promise<void> {
    await this.printConfigSummary();
  }

  private async printConfigSummary(): Promise<void> {
    const logDir = path.join(os.homedir(), '.local', 'share', 'racochu', 'logs');
    const logFile = path.join(logDir, 'racochu.log');

    this.logger.info('📋 Configuration Summary:');
    this.logger.info(`  - Config file: ${this.configFilePath}`);
    this.logger.info(`  - Log file: ${logFile} (symlink → current.log)`);
    const watchSources = this.configService.getWatchSources();
    this.logger.info(`  - Watch sources: ${watchSources.length}`);
    for (const source of watchSources) {
      this.logger.info(`    - ${source.id}: ${source.path} (sourceType=${source.sourceType})`);
    }
    this.logger.info(
      `  - Enrichment: ${this.configService.getEnrichmentConfig().enabled ? 'enabled' : 'disabled'}`,
    );
    this.logger.info(`  - MCP endpoint: ${this.configService.getMcpConfig().url}`);
    this.logger.info(
      `  - Telemetry: ${this.configService.getTelemetryConfig().enabled ? 'enabled' : 'disabled'}`,
    );
  }
}
