package com.genquiz.bk.storage;

import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.source.SourceObjectStorage;
import java.io.*; import java.nio.file.*; import java.security.*; import java.util.*;
import org.apache.tika.Tika; import org.springframework.beans.factory.annotation.Value; import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty; import org.springframework.http.HttpStatus; import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name="bkquiz.storage.provider",havingValue="local",matchIfMissing=true)
public class LocalSourceObjectStorage implements SourceObjectStorage {
 private static final Set<String> ALLOWED=Set.of("application/pdf","application/vnd.openxmlformats-officedocument.wordprocessingml.document","application/vnd.openxmlformats-officedocument.presentationml.presentation","text/plain");
 private final LocalFileStorage storage; private final ClamAvScanner clam; private final Tika tika=new Tika();
 public LocalSourceObjectStorage(@Value("${bkquiz.storage.local-root:./data/uploads}") String root,@Value("${bkquiz.storage.local-temp:./data/tmp}") String temp,ClamAvScanner clam){storage=new LocalFileStorage(Path.of(root),Path.of(temp));this.clam=clam;}
 public StoredObject scanAndStore(String name,String declared,long size,InputStream data)throws IOException{
  Path temp=Files.createTempFile("bkquiz-source-",".tmp");try{Files.copy(data,temp,StandardCopyOption.REPLACE_EXISTING);String detected;try(InputStream in=Files.newInputStream(temp)){detected=tika.detect(in,name);}
   if(!ALLOWED.contains(detected))throw new ApiException(HttpStatus.UNSUPPORTED_MEDIA_TYPE,"UNSUPPORTED_FILE_TYPE","Định dạng thực tế của tài liệu không được hỗ trợ.");clam.requireClean(temp);
   String extension=extension(name);String path;try(InputStream in=Files.newInputStream(temp)){path=storage.store("source",extension,in);}return new StoredObject(path,detected,"LOCAL",sha256(temp));
  }finally{Files.deleteIfExists(temp);}}
 public InputStream read(String key)throws IOException{return storage.read(key);} public void delete(String key){try{storage.delete(key);}catch(IOException ignored){}}
 private String extension(String n){if(n==null)return"";int i=n.lastIndexOf('.');return i>=0&&n.length()-i<=10?n.substring(i).toLowerCase(Locale.ROOT):"";}
 private String sha256(Path p)throws IOException{try{MessageDigest d=MessageDigest.getInstance("SHA-256");try(InputStream in=Files.newInputStream(p)){in.transferTo(new DigestOutputStream(OutputStream.nullOutputStream(),d));}return HexFormat.of().formatHex(d.digest());}catch(NoSuchAlgorithmException e){throw new IllegalStateException(e);}}
}
