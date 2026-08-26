import { Injectable, OnApplicationBootstrap } from '@nestjs/common';
import { UserConfig } from './infrastructure/config/config-schemas';
import { ConfigurationService } from './infrastructure/config/configuration.service';
import { validateUserSources } from './infrastructure/config/user-source.validation';
import { BasePinoLogger } from './infrastructure/logging/base-pino-logger';
import { BensyneClient } from './infrastructure/services/bensyne-client.service';

/**
 * ADR-1 startup guard: Racochu serves exactly one user per host.
 *
 * Enforces the exactly-one user-source invariant (0 → reject, >1 → reject)
 * and ensures the resolved user bank exists at startup — mirroring the
 * `BensyneClient.initialize()` → `registerBank()` pattern used by
 * `FileWatcherService` for watch-source banks.
 */
@Injectable()
export class UserSourceBootstrapService implements OnApplicationBootstrap {
  constructor(
    private readonly configService: ConfigurationService,
    private readonly bensyneClient: BensyneClient,
    private readonly logger: BasePinoLogger,
  ) {}

  async onApplicationBootstrap(): Promise<void> {
    const user = this.configService.getUserConfig();
    await this.bootstrapUserSources(user ? [user] : []);
  }

  /**
   * Explicitly models the "exactly one user per host" contract: takes the
   * declared user sources and rejects startup unless exactly one.
   */
  async bootstrapUserSources(userSources: UserConfig[]): Promise<void> {
    const validation = validateUserSources(userSources);

    if (validation.isKo()) {
      const message = validation.getFormattedErrors();
      this.logger.error(`Startup rejected: ${message}`);
      throw new Error(message);
    }

    const user = validation.getValue();

    // Ensure MCP client is initialized before registering the user bank.
    const initResult = await this.bensyneClient.initialize();
    if (!initResult.isOk()) {
      this.logger.warn(
        `MCP client init failed, user bank registration may retry later: ${initResult.getFormattedErrors()}`,
      );
    }

    const registerResult = await this.bensyneClient.registerBank(
      user.bank,
      `User profile memory for user id="${user.id}"`,
    );
    if (registerResult.isOk()) {
      this.logger.info(`User bank ensured: bank="${user.bank}", userId="${user.id}"`);
    } else {
      this.logger.warn(`Failed to register user bank "${user.bank}": ${registerResult.getFormattedErrors()}`);
    }
  }
}
