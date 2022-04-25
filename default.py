# -*- coding: utf-8 -*-

import platform
import re
import subprocess
import os
import time
import datetime
import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import traceback
import shlex

__addon__ = xbmcaddon.Addon()
__addonID__ = __addon__.getAddonInfo('id')
__addonname__ = __addon__.getAddonInfo('name')
__path__ = __addon__.getAddonInfo('path')
__version__ = __addon__.getAddonInfo('version')
__LS__ = __addon__.getLocalizedString

# PREDEFINES

# Platform and Version
OS = platform.system()
V = platform.version()

# max. Resolution: 4K, Full-HD, HDTV, SDTV (PAL), SDTV (NTSC)
MAXDIM = ['--maxWidth 3840 --maxHeight 2160',
          '--maxWidth 1920 --maxHeight 1080',
          '--maxWidth 1280 --maxHeight 720',
          '--maxWidth 720 --maxHeight 576',
          '--maxWidth 720 --maxHeight 480']

# Compressor
CODEC = ['H.264', 'H.265']

# Encoding quality: High, Normal, Low
QUALITY = ['-q 18', '-q 20', '-q 22', '-q 24', '-q 26']

# foreign audiotracks
ALLTRACKS = '-a 1,2,3,4,5,6,7,8,9,10'

# Converts filesizes to a human readable format (e.g. 123456 bytes to 123.4 KBytes)


def fmt_size(num, suffix='Bytes'):
    for unit in ['', 'K', 'M', 'G', 'T']:
        if abs(num) < 1024:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= float(1024)
    return "%.1f% s%s" % (num, 'T', suffix)


class LoungeRipper(object):

    class NoProfileEnabledException(Exception): pass
    class NoProfileSelectedException(Exception): pass
    class SystemSettingUndefinedException(Exception): pass
    class RemovableMediaNotPresentException(Exception): pass
    class MakemkvExitsNotProperlyException(Exception): pass
    class MakemkvReportsMediumErrorException(Exception): pass
    class HandBrakeCLIExitsNotProperlyException(Exception): pass
    class MkisofsExitsNotProperlyException(Exception): pass
    class RipEncodeProcessStatesToBGException(Exception): pass
    class AbortedRipCompletedException(Exception): pass
    class KillCurrentProcessCalledException(Exception): pass
    class CleanUpTempFolderException(Exception): pass
    class CouldNotFindValidFilesException(Exception): pass
    class CurrentProcessAbortedException(Exception): pass
    class UnexpectedGlobalError(Exception): pass

    def __init__(self):

        self.src = None
        self.tmp = None
        self.destfolder = None
        self.title = None
        self.extensions = ['.mkv', '.ts', '.m2ts', '.mp4', '.mpg', '.mpeg',
                           '.avi', '.flv', '.wmv', '.264', '.mov', '.iso']
        self.task = None
        self.process_all = None
        self.lastmessage = None

        # Profile settings

        self.profile = None
        self.ripper = None
        self.encoder = None
        self.mkiso = None

        # Other

        self.ProgressBG = xbmcgui.DialogProgressBG()
        self.Dialog = xbmcgui.Dialog()
        self.Monitor = xbmc.Monitor()

        # Settings

        self.ripper_executable = os.path.basename(__addon__.getSetting('makemkvcon'))
        self.ripper_path = os.path.join(*(__addon__.getSetting('makemkvcon').split(os.sep))).replace(':', ':\\')
        self.encoder_executable = os.path.basename(__addon__.getSetting('HandBrakeCLI'))
        self.encoder_path = os.path.join(*(__addon__.getSetting('HandBrakeCLI').split(os.sep))).replace(':', ':\\')
        self.mkisofs_executable = os.path.basename(__addon__.getSetting('mkisofs'))
        self.mkisofs_path = os.path.join(*(__addon__.getSetting('mkisofs').split(os.sep))).replace(':', ':\\')

        self.tempfolder = os.path.join(*(__addon__.getSetting('tempfolder')[:-1].split(os.sep))).replace(':', ':\\')
        self.del_tf = True if __addon__.getSetting('deltempfolder').upper() == 'TRUE' else False

        self.nativelanguage = __addon__.getSetting('nativelanguage')
        # Parse the 3 letter language code from selection
        self.lang3 = re.search(r"(.*\()(.*)\)", self.nativelanguage).group(2)

        self.updatelib = True if __addon__.getSetting('updatelib').upper() == 'TRUE' else False
        self.driveid = __addon__.getSetting('driveid')
        self.eject = True if __addon__.getSetting('eject').upper() == 'TRUE' else False

    def getUserProfiles(self):
        _profiles = list()
        if self.getProcessPID(self.ripper_executable) or self.getProcessPID(self.encoder_executable) or \
                self.getProcessPID(self.mkisofs_executable):
            _profiles.append(__LS__(30038))
        else:
            for _profile in ['p1_', 'p2_', 'p3_', 'p4_', 'p5_', 'p6_', 'p7_']:
                if __addon__.getSetting(_profile + 'enabled') == 'true':
                    _profiles.append(__addon__.getSetting(_profile + 'profilename'))
            if xbmcvfs.exists(self.tempfolder) and self.checkTempFolder(): _profiles.append(__LS__(30039))
        if not _profiles:
            raise self.NoProfileEnabledException()

        _idx = xbmcgui.Dialog().select(__LS__(30010), _profiles)
        if _idx == -1:
            raise self.NoProfileSelectedException()

        self.profile = {}
        for _profile in ['p1_', 'p2_', 'p3_', 'p4_', 'p5_', 'p6_', 'p7_']:
            if __addon__.getSetting(_profile + 'profilename') == _profiles[_idx]:
                self.task = _profiles[_idx]
                self.profile['basefolder'] = os.path.join(*(__addon__.getSetting(_profile + 'basefolder')[:-1].split(os.sep))).replace(':', ':\\')
                self.profile['subfolder'] = True if __addon__.getSetting(_profile + 'subfolder').upper() == 'TRUE' else False
                self.profile['codec'] = CODEC[int(__addon__.getSetting(_profile + 'codec'))]
                self.profile['resolution'] = MAXDIM[int(__addon__.getSetting(_profile + 'resolution'))]
                self.profile['quality'] = QUALITY[int(__addon__.getSetting(_profile + 'quality'))]
                self.profile['mintitlelength'] = int(re.match('\d+', __addon__.getSetting(_profile + 'mintitlelength')).group())
                self.profile['mode'] = int(__addon__.getSetting(_profile + 'mode'))
                self.profile['foreignaudio'] = ALLTRACKS if __addon__.getSetting(_profile + 'foreignaudio').upper() == 'TRUE' else ''
                self.profile['additionalhandbrakeargs'] = __addon__.getSetting(_profile + 'additionalhandbrakeargs')

        if _profiles[_idx] == __LS__(30038):
            _procpid = self.getProcessPID(self.ripper_executable)
            if _procpid:
                self.notifyLog('Killing ripper process with PID %s' % _procpid.decode())
                self.killProcessPID(_procpid, process=self.ripper_executable)
            _procpid = self.getProcessPID(self.encoder_executable)
            if _procpid:
                self.notifyLog('Killing encoder process with PID %s' % _procpid.decode())
                self.killProcessPID(_procpid, process=self.encoder_executable)
            _procpid = self.getProcessPID(self.mkisofs_executable)
            if _procpid:
                self.notifyLog('Killing mkisofs process with PID %s' % _procpid.decode())
                self.killProcessPID(_procpid, process=self.mkisofs_executable)
            raise self.KillCurrentProcessCalledException()

        if _profiles[_idx] == __LS__(30039):
            self.rmdirs(self.tempfolder, force=True)
            raise self.CleanUpTempFolderException()

    def notifyLog(self, message, level=xbmc.LOGDEBUG):
        xbmc.log('[%s] %s' % (__addonID__, message), level)

    def checkSystemSettings(self, mode):

        if mode in [0, 1, 3] and not self.ripper_executable:
            raise self.SystemSettingUndefinedException()
        elif mode in [2] and not self.encoder_executable:
            raise self.SystemSettingUndefinedException()
        elif mode in [3] and not self.mkisofs_executable:
            raise self.SystemSettingUndefinedException()

        if not self.tempfolder or not self.profile['basefolder']:
            raise self.SystemSettingUndefinedException()

    def getProcessPID(self, process):
        if not process: return False
        if OS == 'Linux':
            _syscmd = subprocess.Popen(['pidof', process], stdout=subprocess.PIPE)
            PID = _syscmd.stdout.read().strip().decode()
            return False if not PID else PID
        elif OS == 'Windows':
            _tlcall = 'TASKLIST', '/FI', 'imagename eq %s' % os.path.basename(process)
            _syscmd = subprocess.Popen(_tlcall, shell=True, stdout=subprocess.PIPE)
            PID = _syscmd.communicate()[0].strip().splitlines()
            if len(PID) > 1 and os.path.basename(process) in PID[-1].decode():
                return PID[-1].split()[1]
            else: return False
        else:
            self.notifyLog('Running on %s, could not determine PID of %s' % (OS, process))
            return False

    def killProcessPID(self, pid, process=None):
        if OS == 'Linux':
            _syscmd = subprocess.call('kill -9 %s' % pid, shell=True)
        elif OS == 'Windows':
            _syscmd = subprocess.call('TASKKILL /F /IM %s' % os.path.basename(process), shell=True)
        else: pass

    def rmdirs(self, folder, force=True):
        dirs, files = xbmcvfs.listdir(folder)
        for file in files: xbmcvfs.delete(os.path.join(folder, file))
        for dir in dirs:
            self.rmdirs(os.path.join(folder, dir), force=force)
            os.rmdir(os.path.join(folder, dir))
        return

    def checkTempFolder(self):
        dirs, files = xbmcvfs.listdir(self.tempfolder)
        return dirs or files

    def delTempFolder(self, force=False, file=None):
        #
        # delete old temp files recursive if there any, but only if there's no previous rip/encode running
        #
        if self.getProcessPID(self.ripper_executable) or self.getProcessPID(self.encoder_executable) or \
                self.getProcessPID(self.mkisofs_executable):
            self.notifyLog('Couldn\'t clearing up folder %s, ripper, encoder or mkisofs active' % self.tempfolder)
            return False
        elif not (self.del_tf or force):
            self.notifyLog('Not allowed clearing up folder %s due settings' % self.tempfolder)
            return False
        elif file is not None and self.del_tf:
            xbmcvfs.delete(file)
            return True
        elif force:
            self.rmdirs(self.tempfolder, force=force)
            return True
        else:
            return False

    def buildDestFileAndFolder(self, title=''):
        rips = list()
        content = xbmcvfs.listdir(self.tempfolder)
        for files in content[1]:
            if os.path.splitext(files)[1] in self.extensions: rips.append(files)

        _fsize = 0
        self.notifyLog('Search for the largest file in %s' % self.tempfolder)
        for rip in rips:
            file = xbmcvfs.File(os.path.join(self.tempfolder, rip))
            self.notifyLog('File: %s - %s' % (rip, fmt_size(file.size())))
            if file.size() > _fsize:
                _fsize = file.size()
                self.src = rip
            file.close()

        if len(rips) > 1:
            if self.profile['mode'] == 0 or self.profile['mode'] == 1:
                self.notifyLog('Suggest that %s with a size of %s is main movie' % (self.src, fmt_size(_fsize)))

            # Ask for multiple processing if it's not done before

            if self.profile['mode'] > 0 and self.del_tf and self.process_all is None:
                self.process_all = False if self.Dialog.yesno(__addonname__, __LS__(30059), autoclose=60000) == 0 else True
                self.notifyLog('Process multiple files: %s' % self.process_all)

        if _fsize > 0:
            self.title = datetime.datetime.now().strftime('%Y-%m-%d.%H-%M-%S')
            _basename = '.'.join(self.src.split('.')[0:-1])
            if '_t0' in _basename: _basename = _basename[:-4]
            if 'title' in _basename and title == '':
                kb = xbmc.Keyboard('', __LS__(30030))
                kb.doModal()
                if kb.isConfirmed() and kb.getText() != '': self.title = kb.getText()
            elif 'title' not in _basename:
                self.title = _basename
            elif title:
                self.title = title

            self.title = self.title.replace('_', ' ')
            self.title = " ".join(word.capitalize() for word in self.title.split())

            self.destfile = self.title + os.path.splitext(self.src)[1]
            if self.profile['subfolder']:
                self.destfolder = os.path.join(self.profile['basefolder'], self.title)
            else:
                self.destfolder = self.profile['basefolder']
            if not xbmcvfs.exists(self.destfolder): xbmcvfs.mkdirs(self.destfolder)
        else:
            raise self.CouldNotFindValidFilesException()

    def pollSubprocess(self, process_exec, process_path, process, header):
        _val = ''
        message = __LS__(30063)
        _m = __LS__(30063)
        percent = 0
        _p = 0
        _startsb = time.mktime(time.localtime())
        self.ProgressBG.create('%s - %s' % (__addonname__, header), message)

        proc = subprocess.Popen(shlex.split(process), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                executable=process_path, encoding='utf-8', text=True)
        while proc.poll() is None:
            if self.Monitor.abortRequested(): break
            try:
                if percent != _p or message != _m:
                    if percent > 0.4 and message == 'Encoding':
                        _elapsed = time.mktime(time.localtime()) - _startsb
                        _remaining = datetime.timedelta(seconds=int(100 * _elapsed/percent - _elapsed))
                        self.ProgressBG.update(int(percent), '%s - %s' % (__addonname__, header),
                                               __LS__(30029) % (message, _remaining))
                        self.notifyLog('%s: %s%% done (%s remaining)' % (message, percent, _remaining))
                    else:
                        self.ProgressBG.update(int(percent), '%s - %s' % (__addonname__, header),
                                               __LS__(30066) % message)
                        self.notifyLog('%s: %s%% done' % (message, percent))

                    _p = percent
                    _m = message

                msg = proc.stdout.readline().rstrip()
                data = msg.split(':')
                if 'PRGC' in data[0]:
                    _val = data[1].split(',')
                    message = _val[2].replace('"', '')
                elif 'PRGT' in data[0]:
                    _val = data[1].split(',')
                    message = _val[2].replace('"', '')
                elif 'PRGV' in data[0]:
                    _val = data[1].split(',')
                    percent = int(_val[0]) * 100 // int(_val[2])
                elif 'Encoding' in data[0]:
                    message = data[0]
                    _val = data[1].split(',')
                    percent = float(re.match('^ [0-9]+(.[0-9])', _val[1]).group())
                elif 'done, ' in data[0]:
                    message = 'create ISO'
                    percent = float(re.match('^[0-9]+(.[0-9])', data[0].lstrip()).group())
                elif 'MSG' in data[0]:
                    _val = data[1].split(',')
                    self.notifyLog(_val[3].replace('"', ''))
                    self.lastmessage = _val[3].replace('"', '')
                    if 'MEDIUM ERROR' in _val[3] or 'HARDWARE ERROR' in _val[3]:
                        self.ProgressBG.close()
                        raise self.MakemkvReportsMediumErrorException
                else:
                    pass

            except (UnicodeDecodeError, ValueError) as e:
                self.notifyLog('Ignore process error: %s' % str(e))
                continue

        self.ProgressBG.close()
        self.notifyLog('%s finished with status %s' % (process_exec, proc.poll()))
        return proc.poll()

    def copyfile(self, source, dest):
        chunks = 0

        self.notifyLog('Copy file from \'%s\' to \'%s\'' % (source, dest))
        try:
            if os.path.exists(source):
                chunksize = os.path.getsize(source) // 100
                self.ProgressBG.create('%s - %s' % (__addonname__, __LS__(30066) % self.title), __LS__(30067))

                with open(source, 'rb') as src, xbmcvfs.File(dest, 'w') as dst:
                    while True:
                        self.ProgressBG.update(chunks, '%s - %s' % (__addonname__, __LS__(30066) % self.title), __LS__(30067))
                        chunk = bytearray(src.read(chunksize))
                        if not chunk:
                            self.notifyLog('%s chunks transmitted' % chunks)
                            break
                        dst.write(chunk)
                        chunks += 1
            else:
                raise self.CouldNotFindValidFilesException
        except Exception:
            self.notifyLog('An error has occurred: %s' % traceback.format_exc(), xbmc.LOGERROR)
            self.ProgressBG.close()
            raise self.CurrentProcessAbortedException()

        self.ProgressBG.close()
        if self.del_tf: self.delTempFolder(file=source)

    def start(self):

        self.notifyLog('Engage Lounge Ripper %s on %s %s' % (__version__, OS, V))
        self.getUserProfiles()
        self.checkSystemSettings(self.profile['mode'])
        self.notifyLog('starting task \'%s\' (mode %s)' % (self.task, self.profile['mode']))

        if self.profile['mode'] == 0 or self.profile['mode'] == 1 or self.profile['mode'] == 3:
            #
            # RIP ONLY / RIP AND ENCODE / BACKUP
            #
            # Check if media is present in drive [driveno]
            # raise self.MediaIsNotPresentException if isn't

            _foundmedia = False
            try:
                print('"%s" info list -r' % self.ripper_executable, self.ripper_path)
                _rv = subprocess.check_output('"%s" info list -r' % self.ripper_executable,
                                              stderr=subprocess.STDOUT, executable=self.ripper_path)
            except subprocess.CalledProcessError as e:
                _rv = e.output

            for _line in iter(_rv.splitlines()):
                _item = _line.decode('utf-8').replace('"', '').split(',')
                if 'DRV:' in _item[0] and _item[5] != '':
                    self.notifyLog('Reported media on \'%s\': %s' % (_item[6], _item[5]))
                    _foundmedia = True
                    self.title = _item[5]
                    break

            if not _foundmedia: raise self.RemovableMediaNotPresentException()

            if self.checkTempFolder():
                if self.Dialog.yesno(__addonname__, __LS__(30092), autoclose=60000): self.delTempFolder(force=True)

            self.ripper = '"%s" mkv -r --messages=-stdout --progress=-same --decrypt disc:%s all ' \
                          '--minlength=%s "%s"' % \
                          (self.ripper_executable,
                           self.driveid,
                           self.profile['mintitlelength'],
                           self.tempfolder)

            if self.profile['mode'] == 3:
                isofolder = os.path.join(self.tempfolder, 'ISO')
                if not xbmcvfs.exists(isofolder): xbmcvfs.mkdirs(isofolder)
                self.ripper = '"%s" backup -r --decrypt --cache=16 --noscan --progress=-same disc:%s "%s"'\
                              % (self.ripper_executable, self.driveid, isofolder)

            self.notifyLog('Ripper command line: %s' % self.ripper)

            _rv = self.pollSubprocess(self.ripper_executable, self.ripper_path, self.ripper, self.title)
            if _rv is None:
                raise self.RipEncodeProcessStatesToBGException()
            if _rv != 0: raise self.MakemkvExitsNotProperlyException(self.lastmessage)
            if self.eject:
                xbmc.executebuiltin('EjectTray()')
                self.notifyLog('Eject disc')

        if self.profile['mode'] == 0 or self.profile['mode'] == 3:
            if self.profile['mode'] == 3:
                #
                # Make ISO
                #
                isofile = os.path.join(self.tempfolder, self.title + '.iso')
                self.mkiso = '"%s" -UDF -R -J -input-charset utf-8 -iso-level 3 -V "%s" -o "%s" "%s"' \
                             % (self.mkisofs_executable, self.title.upper(), isofile, isofolder)

                self.notifyLog('mkisofs command line: %s' % self.mkiso)
                _rv = self.pollSubprocess(self.mkisofs_executable, self.mkisofs_path, self.mkiso, self.title)
                if _rv is None:
                    raise self.RipEncodeProcessStatesToBGException()
                if _rv != 0: self.MkisofsExitsNotProperlyException()

                # remove ISO folder
                if self.del_tf: self.rmdirs(isofolder, force=True)

            self.buildDestFileAndFolder(title=self.title)
            #
            # RIP ONLY / BACKUP - WE ARE READY
            #
            self.notifyLog('Encoding of \'%s\' not required in this profile' % self.destfile)
            self.copyfile(os.path.join(self.tempfolder, self.src), os.path.join(self.destfolder, self.destfile))

        while True:
            if self.profile['mode'] == 1 or self.profile['mode'] == 2:
                #
                # RIP AND ENCODE / ENCODE ONLY
                #
                if self.profile['mode'] == 1:
                    #
                    # RIP/ENCODE - EXPECT FILE(S) IN TEMPFOLDER, USING LARGEST
                    #
                    self.process_all = False

                self.buildDestFileAndFolder()

                self.tmp = str(int(time.time()))
                self.encoder = '"%s" -i "%s" -o "%s" -f mkv --decomb fast -N %s --native-dub -m ' \
                               '-Z "%s MKV 2160p60" -s 1 %s %s %s %s 2>&1' % \
                               (self.encoder_executable,
                                os.path.join(self.tempfolder, self.src),
                                os.path.join(self.tempfolder, self.tmp),
                                self.lang3,
                                self.profile['codec'],
                                self.profile['foreignaudio'],
                                self.profile['quality'],
                                self.profile['resolution'],
                                self.profile['additionalhandbrakeargs'])

                self.notifyLog('Encoder command line: %s' % self.encoder)

                _rv = self.pollSubprocess(self.encoder_executable, self.encoder_path, self.encoder, self.destfile)
                if _rv is None:
                    raise self.RipEncodeProcessStatesToBGException()
                if _rv != 0:
                    raise self.HandBrakeCLIExitsNotProperlyException()
                self.copyfile(os.path.join(self.tempfolder, self.tmp), os.path.join(self.destfolder, self.destfile))
                if self.del_tf: self.delTempFolder(force=True, file=os.path.join(self.tempfolder, self.src))
                #
                # READY
                #
            self.Dialog.notification(__addonname__, __LS__(30049) % (__addonname__, self.task), xbmcgui.NOTIFICATION_INFO)
            if self.process_all is None or not self.process_all: break

        if self.updatelib: xbmc.executebuiltin('UpdateLibrary(video)')
        self.notifyLog('switch off Lounge Ripper')

##########################################################################################################
#                                                                                                        #
#                                                         MAIN                                           #
#                                                                                                        #
##########################################################################################################


Ripper = LoungeRipper()

try:
    Ripper.start()
except Ripper.NoProfileEnabledException:
    ok = Ripper.Dialog.ok(__addonname__, __LS__(30050))
    Ripper.notifyLog('No profiles enabled', level=xbmc.LOGERROR)
except Ripper.NoProfileSelectedException:
    Ripper.notifyLog('No profile selected, exit %s' % __addonname__)
except Ripper.SystemSettingUndefinedException:
    ok = Ripper.Dialog.ok(__addonname__, __LS__(30052))
    Ripper.notifyLog('One or more system settings are invalid', level=xbmc.LOGERROR)
except Ripper.CouldNotFindValidFilesException:
    ok = Ripper.Dialog.ok(__addonname__, __LS__(30056) % Ripper.tempfolder)
    Ripper.notifyLog('Could not find any valid files in %s' % Ripper.tempfolder, level=xbmc.LOGERROR)
except Ripper.RemovableMediaNotPresentException:
    Ripper.notifyLog('Could not detect removable media or media isn\'t present or not readable', level=xbmc.LOGERROR)
    ok = Ripper.Dialog.ok(__addonname__, __LS__(30057))
except Ripper.MakemkvReportsMediumErrorException:
    ok = Ripper.Dialog.ok(__addonname__, __LS__(30069))
    Ripper.notifyLog('MakeMKV has reported a medium error', level=xbmc.LOGERROR)
except Ripper.MakemkvExitsNotProperlyException:
    ok = Ripper.Dialog.ok(__addonname__, __LS__(30053))
    Ripper.notifyLog('%s don\'t work as expected, possibly too old, '
                     'key invalid, aborted by user '
                     'or another error has occured: %s' % (Ripper.ripper_executable, Ripper.lastmessage),
                     level=xbmc.LOGERROR)
except Ripper.HandBrakeCLIExitsNotProperlyException:
    ok = Ripper.Dialog.ok(__addonname__, __LS__(30054))
    Ripper.notifyLog('An error occured while encoding with %s' % Ripper.encoder_executable, level=xbmc.LOGERROR)
except Ripper.MkisofsExitsNotProperlyException:
    ok = Ripper.Dialog.ok(__addonname__, __LS__(30062))
    Ripper.notifyLog('An error occured while processing %s' % Ripper.mkisofs_executable, level=xbmc.LOGERROR)
except Ripper.RipEncodeProcessStatesToBGException:
    Ripper.notifyLog('Rip/Encode processes turns into a background process')
    Ripper.notifyLog('After this toolchain may be broken and incomplete')
    Ripper.notifyLog('You can continue processing of toolchain afterwards')
except Ripper.KillCurrentProcessCalledException:
    Ripper.notifyLog('All current ripper and encoders terminated')
except Ripper.CleanUpTempFolderException:
    Ripper.Dialog.notification(__addonname__, __LS__(30046) % Ripper.tempfolder, xbmcgui.NOTIFICATION_INFO)
    Ripper.notifyLog('Temporary folder %s cleaned' % Ripper.tempfolder)
except Ripper.CurrentProcessAbortedException:
    Ripper.Dialog.notification(__addonname__, __LS__(30058), xbmcgui.NOTIFICATION_ERROR)
    Ripper.notifyLog('Last operation could not completed. Check results', level=xbmc.LOGERROR)
except Exception as e:
    Ripper.notifyLog('An error has occurred: %s' % traceback.format_exc(), xbmc.LOGERROR)
del Ripper
