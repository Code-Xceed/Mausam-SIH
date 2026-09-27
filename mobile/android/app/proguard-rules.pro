# Mausam Next-Gen R8 rules (TASK-077)
# Flutter + plugins keep-rules ship with their own consumer rules; these are
# app-specific keeps for the FCM receiver and the home-widget provider.

-keep class in.gov.mausam.nextgen.** { *; }
-keep class com.google.firebase.** { *; }
-dontwarn com.google.firebase.**

# maplibre native bridge
-keep class org.maplibre.** { *; }
-dontwarn org.maplibre.**
