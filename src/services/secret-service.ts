/*
* This class provides the authentication process the secret for a given key.
*/
export class SecretService {
    /*
    * For this implementation, we are just using a static map that holds the key/values.
    * In reality, you will want to store these somewhere else, like S3, or some other
    * secrets manager.
    */
    static secrets = new Map();

    static {
        SecretService.secrets.set('ApiKey1', 'Secret1');
        SecretService.secrets.set('ApiKey2', '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8');
    }

    getSecretForKey(key: string): Uint8Array {
        const secretString = SecretService.secrets.get(key) || '';

        return Buffer.from(secretString);
    }
}