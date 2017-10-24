# Authors: 
#   Trevor Perrin
#   Google - parsing subject field
#
# See the LICENSE file for legal information regarding use of this file.

"""Class representing an X.509 certificate."""

from .utils.asn1parser import ASN1Parser
from .utils.cryptomath import *
from .utils.keyfactory import _createPublicRSAKey
from .utils.pem import *
from ecdsa.keys import VerifyingKey
from ecdsa.curves import NIST256p, NIST384p, NIST521p

class X509(object):
    """
    This class represents an X.509 certificate.

    :vartype bytes: bytearray
    :ivar bytes: The DER-encoded ASN.1 certificate

    :vartype publicKey: ~tlslite.utils.rsakey.RSAKey
    :ivar publicKey: The subject public key from the certificate.

    :vartype subject: bytearray
    :ivar subject: The DER-encoded ASN.1 subject distinguished name.

    :vartype certAlg: str
    :ivar certAlg: algorithm of the public key, "rsa" for RSASSA-PKCS#1 v1.5
        and "rsa-pss" for RSASSA-PSS
    """

    def __init__(self):
        """Create empty certificate object."""
        self.bytes = bytearray(0)
        self.publicKey = None
        self.subject = None
        self.certAlg = None

    def parse(self, s):
        """
        Parse a PEM-encoded X.509 certificate.

        :type s: str
        :param s: A PEM-encoded X.509 certificate (i.e. a base64-encoded
            certificate wrapped with "-----BEGIN CERTIFICATE-----" and
            "-----END CERTIFICATE-----" tags).
        """
        bytes = dePem(s, "CERTIFICATE")
        self.parseBinary(bytes)
        return self

    def parseBinary(self, bytes):
        """
        Parse a DER-encoded X.509 certificate.

        :type bytes: str or L{bytearray} of unsigned bytes
        :param bytes: A DER-encoded X.509 certificate.
        """
        self.bytes = bytearray(bytes)
        p = ASN1Parser(bytes)

        #Get the tbsCertificate
        tbsCertificateP = p.getChild(0)

        #Is the optional version field present?
        #This determines which index the key is at.
        if tbsCertificateP.value[0]==0xA0:
            subjectPublicKeyInfoIndex = 6
        else:
            subjectPublicKeyInfoIndex = 5

        #Get the subject
        self.subject = tbsCertificateP.getChildBytes(\
                           subjectPublicKeyInfoIndex - 1)

        #Get the subjectPublicKeyInfo
        subjectPublicKeyInfoP = tbsCertificateP.getChild(\
                                    subjectPublicKeyInfoIndex)

        # Get the AlgorithmIdentifier
        algIdentifier = subjectPublicKeyInfoP.getChild(0)
        algIdentifierLen = algIdentifier.getChildCount()
        # first item of AlgorithmIdentifier is the algorithm
        alg = algIdentifier.getChild(0)
        algOID = alg.value
        if list(algOID) == [42, 134, 72, 134, 247, 13, 1, 1, 1]:
            self.certAlg = "rsa"
        elif list(algOID) == [42, 134, 72, 134, 247, 13, 1, 1, 10]:
            self.certAlg = "rsa-pss"
        elif list(algOID) == [42, 134, 72, 206, 61, 2, 1]:
            self.certAlg = "ecdsa"
        else:
            raise SyntaxError("Unrecognized AlgorithmIdentifier")

        # for RSA the parameters of AlgorithmIdentifier should be a NULL
        if self.certAlg == "rsa":
            if algIdentifierLen != 2:
                raise SyntaxError("Missing parameters in AlgorithmIdentifier")
            params = algIdentifier.getChild(1)
            if params.value != bytearray(0):
                raise SyntaxError("Unexpected non-NULL parameters in "
                                  "AlgorithmIdentifier")
        elif self.certAlg == "ecdsa":
            if algIdentifierLen != 2:
                raise SyntaxError("Missing parameters in AlgorithmIdentifier")
            curveId = algIdentifier.getChild(1)
            if list(curveId.value) == [42, 134, 72, 206, 61, 3, 1, 7]:
                self._ecdsaPubKeyParsing(subjectPublicKeyInfoP, NIST256p)
            elif list(curveId.value) == [43, 129, 4, 0, 34]:
                self._ecdsaPubKeyParsing(subjectPublicKeyInfoP, NIST384p)
            elif list(curveId.value) == [43, 129, 4, 0, 35]:
                self._ecdsaPubKeyParsing(subjectPublicKeyInfoP, NIST521p)
            else:
                raise SyntaxError("Unknown elliptic curve")

            return
        else:  # rsa-pss
            pass  # ignore parameters, if any - don't apply key restrictions

        self._rsaPubKeyParsing(subjectPublicKeyInfoP)

    def _rsaPubKeyParsing(self, subjectPublicKeyInfoP):

        #Get the subjectPublicKey
        subjectPublicKeyP = subjectPublicKeyInfoP.getChild(1)

        #Adjust for BIT STRING encapsulation
        if (subjectPublicKeyP.value[0] !=0):
            raise SyntaxError()
        subjectPublicKeyP = ASN1Parser(subjectPublicKeyP.value[1:])

        #Get the modulus and exponent
        modulusP = subjectPublicKeyP.getChild(0)
        publicExponentP = subjectPublicKeyP.getChild(1)

        #Decode them into numbers
        n = bytesToNumber(modulusP.value)
        e = bytesToNumber(publicExponentP.value)

        #Create a public key instance
        self.publicKey = _createPublicRSAKey(n, e)

    def _ecdsaPubKeyParsing(self, subjectPublicKeyInfoP, curve):
        derPubKey = subjectPublicKeyInfoP.getChild(1).value
        if derPubKey[:2] != b'\000\004':
            raise SyntaxError("Unexpected public key encoding")
        self.publicKey = VerifyingKey.from_string(derPubKey[2:], curve)
        pass

    def getFingerprint(self):
        """
        Get the hex-encoded fingerprint of this certificate.

        :rtype: str
        :returns: A hex-encoded fingerprint.
        """
        return b2a_hex(SHA1(self.bytes))

    def writeBytes(self):
        """Serialise object to a DER encoded string."""
        return self.bytes


