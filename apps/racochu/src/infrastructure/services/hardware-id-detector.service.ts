import { Injectable } from '@nestjs/common';
import { randomUUID } from 'crypto';
import { getMachineId } from 'native-machine-id';

@Injectable()
export class HardwareIdDetectorService {
  private hardwareId: string | null = null;

  async getHardwareId(): Promise<string> {
    if (this.hardwareId !== null) {
      return this.hardwareId;
    }

    try {
      this.hardwareId = (await getMachineId()) ?? randomUUID();
    } catch {
      this.hardwareId = randomUUID();
    }

    return this.hardwareId;
  }
}
