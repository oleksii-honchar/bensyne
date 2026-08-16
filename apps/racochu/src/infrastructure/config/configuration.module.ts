import { Module } from '@nestjs/common';
import { AppConfig } from '../../app.config';
import { LoggerModule } from '../logging/logger.module';
import { ConfigurationService } from './configuration.service';

@Module({
  imports: [LoggerModule],
  providers: [
    ConfigurationService,
    {
      provide: 'CONFIG_FILE_PATH',
      useFactory: (appConfig: AppConfig) => appConfig.appConfigPath,
      inject: [AppConfig.KEY],
    },
  ],
  exports: [ConfigurationService, 'CONFIG_FILE_PATH'],
})
export class ConfigurationModule {}
